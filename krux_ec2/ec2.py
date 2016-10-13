# -*- coding: utf-8 -*-
#
# © 2015 Krux Digital, Inc.
#

#
# Standard libraries
#

from __future__ import absolute_import

#
# Third party libraries
#

from decorator import decorator

#
# Internal libraries
#

from krux_boto import Boto3, add_boto_cli_arguments
from krux.logging import get_logger
from krux.stats import get_stats
from krux.cli import get_parser, get_group
from krux_ec2.filter import Filter
from krux.object import Object


NAME = 'krux-ec2'


@decorator
def map_search_to_filter(wrapped, *args, **kwargs):
    """
    Replace a search argument with an instance of Filter.

    NOTE: This only works on methods that have a signature that is just
    self and the search criteria; it doesn't pass on kwargs and you can't
    mangle args as it's a tuple.
    """
    search_filter = None
    if isinstance(args[1], list):
        search_filter = Filter()
        for term in args[1]:
            search_filter.parse_string(term)
    elif isinstance(args[1], dict):
        search_filter = Filter(initial=args[1])
    elif isinstance(args[1], Filter):
        search_filter = args[1]
    else:
        raise NotImplementedError('This method cannot handle parameter of type {0}'.format(type(args[1]).__name__))

    return wrapped(args[0], search_filter)


def get_ec2(args=None, logger=None, stats=None):
    """
    Return a usable EC2 object without creating a class around it.

    In the context of a krux.cli (or similar) interface the 'args', 'logger'
    and 'stats' objects should already be present. If you don't have them,
    however, we'll attempt to provide usable ones for the SQS setup.

    (If you omit the add_ec2_cli_arguments() call during other cli setup,
    the Boto object will still work, but its cli options won't show up in
    --help output)

    (This also handles instantiating a Boto object on its own.)
    """
    if not args:
        parser = get_parser()
        add_ec2_cli_arguments(parser)
        args = parser.parse_args()

    if not logger:
        logger = get_logger(name=NAME)

    if not stats:
        stats = get_stats(prefix=NAME)

    boto = Boto3(
        log_level=args.boto_log_level,
        access_key=args.boto_access_key,
        secret_key=args.boto_secret_key,
        region=args.boto_region,
        logger=logger,
        stats=stats,
    )
    return EC2(
        boto=boto,
        logger=logger,
        stats=stats,
    )


def add_ec2_cli_arguments(parser, include_boto_arguments=True):
    """
    Utility function for adding EC2 specific CLI arguments.
    """
    if include_boto_arguments:
        # GOTCHA: Since EC2 and S3 both uses Boto, the Boto's CLI arguments can be included twice,
        # causing an error. This creates a way to circumvent that.

        # Add all the boto arguments
        add_boto_cli_arguments(parser)

    # Add those specific to the application
    group = get_group(parser, NAME)


class EC2(Object):
    """
    A manager to handle all EC2 related functions.
    Each instance is locked to a connection to a designated region (self.boto.cli_region).
    """

    # Timeout value in milliseconds for waiting for EC2 items to be ready
    TIMEOUT = 120000  # 2 minutes

    # Number of milliseconds to wait in between 2 checks
    CHECK_INTERVAL = 3000  # 3 seconds

    # This is the IAM role that the instance is started up with. The bootstrap
    # role is needed so that bootstrap.py can update the instance's tags with
    # its status.
    INSTANCE_PROFILE_NAME = 'bootstrap'

    def __init__(
        self,
        boto,
        logger=None,
        stats=None,
    ):
        # Call to the superclass to bootstrap.
        super(EC2, self).__init__(name=NAME, logger=logger, stats=stats)

        # Throw exception when Boto3 is not used
        if not isinstance(boto, Boto3):
            raise TypeError('krux_ec2.ec2.EC2 only supports krux_boto.boto.Boto3')

        self.boto = boto

        # Set up default cache
        self._resource = None
        self._client = None

    def _get_resource(self):
        """
        Returns a resource to the designated region (self.boto.cli_region).
        The connection is established on the first call for this instance (lazy) and cached.
        """
        if self._resource is None:
            self._resource = self.boto.resource(service_name='ec2', region_name=self.boto.cli_region)

        return self._resource

    def _get_client(self):
        """
        Returns a client to the designated region (self.boto.cli_region).
        The connection is established on the first call for this instance (lazy) and cached.
        """
        if self._client is None:
            self._client = self.boto.client(service_name='ec2', region_name=self.boto.cli_region)

        return self._client

    @map_search_to_filter
    def find_instances(self, instance_filter):
        """
        Returns a list of instances that matches the search criteria.

        The search parameter must be either a krux_ec2.filter.Filter instance or
        a dictionary or a list that krux_ec2.filter.Filter class can handle.
        Refer to the docstring on the class.

        .. seealso:: https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ServiceResource.instances

        :param instance_filter: The parameter to search by. Refer to the docstring on the class for more.
        :type instance_filter: krux_ec2.filter.Filter | dict | list
        """

        self._logger.debug('Filters to use: %s', dict(instance_filter))

        instances = list(self._get_resource().instances.filter(Filters=instance_filter.to_filter()))

        self._logger.info('Found following instances: %s', instances)

        return instances

    def find_instances_by_hostname(self, hostname):
        """
        Helper method for looking up instances by hostname.

        :param hostname: The hostname to look for
        :type hostname: str
        """
        return self.find_instances({
            'tag:Name': [hostname],
            'instance-state-name': ['running', 'stopped'],
        })

    def run_instance(self, ami_id, cloud_config, instance_type, sec_group, zone):
        """
        Starts an instance in the given AMI.

        The ami_id parameter is the ID of the AMI image where the new instance will be created.
        The cloud_config parameter is passed as the user data.
        The instance_type, sec_group, and zone are passed as respective parameters to AWS.

        4 block devices are created as ephemeral and passed.

        .. seealso:: https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ServiceResource.create_instances
        """
        # OK, so, on larger instances, extra devices only show up if you tell them to associate with a block device.
        # These EBS AMIs don't set this up, so we have to. sdb will always be ephemeral0,
        # which is how we've always done it. If there are more devices, they will get sdc,sdd,sde.
        # NOTE: see mounts.pp in kbase for how-we-deal-with-these.
        # TODO: Turn this into a const
        block_device_map = [{
            'VirtualName': 'ephemeral0',
            'DeviceName': '/dev/sdb',
        }, {
            'VirtualName': 'ephemeral1',
            'DeviceName': '/dev/sdc',
        }, {
            'VirtualName': 'ephemeral2',
            'DeviceName': '/dev/sdd',
        }, {
            'VirtualName': 'ephemeral3',
            'DeviceName': '/dev/sde',
        }]

        resource = self._get_resource()
        instances = resource.create_instances(
            ImageId=ami_id,
            MinCount=1,
            MaxCount=1,
            InstanceType=instance_type,
            UserData=cloud_config,
            SecurityGroups=[sec_group],
            BlockDeviceMappings=block_device_map,
            IamInstanceProfile={'Name': self.INSTANCE_PROFILE_NAME},
            Placement={'AvailabilityZone': zone},
        )

        instance = instances[0]
        self._logger.debug('Waiting for the instance %s to be ready...', instance.id)

        waiter = self._get_client().get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance.id])
        instance.reload()

        self._logger.info('Started instance %s', instance.public_dns_name)

        return instance

    def attach_ebs_volume(
        self,
        instance,
        device,
        save_on_termination,
        volume_id=None,
        volume_size=None,
    ):
        """
        Attach a designated EBS volume to the given instance at the given device.

        If volume_id parameter is provided, the corresponding EBS volume is attached.
        If not, a new volume with the give volume_size is created and attached.
        Either volume_id parameter or volume_size parameter is required.

        If save_on_termination parameter is true, then the EBS volume is saved (not deleted)
        upon the instance termination.
        """
        if volume_id is not None:
            # GOTCHA: volume_id takes priority over volume_size
            volume = self.find_ebs_volumes({'volume-id': [volume_id]})[0]
        elif volume_size is not None:
            volume = self._get_resource().create_volume(
                Size=volume_size,
                AvailabilityZone=instance.placement['AvailabilityZone'],
                VolumeType='gp2',
            )

            self._logger.debug('Waiting for the EBS volume %s to be ready...', volume.id)
            waiter = self._get_client().get_waiter('volume_available')
            waiter.wait(VolumeIds=[volume.id])

            volume.reload()
        else:
            raise ValueError('Either volume_id or volume_size is required')

        volume.attach_to_instance(InstanceId=instance.id, Device=device)

        self._logger.debug('Waiting for the EBS volume to be attached...')
        waiter = self._get_client().get_waiter('volume_in_use')
        waiter.wait(VolumeIds=[volume.id])

        instance.modify_attribute(BlockDeviceMappings=[{
            'DeviceName': device,
            'Ebs': {
                'VolumeId': volume.id,
                'DeleteOnTermination': not save_on_termination,
            },
        }])

        self._logger.info(
            'Attached EBS volume %s to instance %s at %s',
            volume.id, instance.public_dns_name, device
        )

        return volume

    @map_search_to_filter
    def find_ebs_volumes(self, ebs_filter):
        """
        Returns a list of EBS volumes that matches the search criteria.

        The search parameter must be either a krux_ec2.filter.Filter instance or
        a dictionary or a list that krux_ec2.filter.Filter class can handle.
        Refer to the docstring on the class.

        .. seealso:: https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ServiceResource.volumes
        """

        self._logger.debug('Filters to use: %s', dict(ebs_filter))

        volumes = list(self._get_resource().volumes.filter(Filters=ebs_filter.to_filter()))

        self._logger.info('Found following volumes: %s', volumes)

        return volumes

    def find_security_group(self, security_group):
        """
        Returns a list of security groups with the given group name.

        Performs a contains search rather than exact match.

        .. seealso:: https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ServiceResource.security_groups
        """
        security_filter = Filter()
        security_filter.add_filter('group-name', security_group)

        self._logger.debug('Filters to use: %s', dict(security_filter))

        sec_groups = list(self._get_resource().security_groups.filter(Filters=security_filter.to_filter()))

        self._logger.info('Found following security groups: %s', sec_groups)

        return sec_groups

    def find_elastic_ips(self, instance):
        """
        Find the Elastic IP(s) mapped to a given instance.

        Will return a list of boto.ec2.address.Address for every Elastic IP
        that is matched to the instance.id provided. Returns an empty list
        if no Elastic IPs are mapped to a given instnce.

        Please note that VPC supports up to 30 IPs per host, which means you
        will not always get a single IP back.
        """
        return instance.classic_address

    def update_elastic_ip(self, address, new_instance):
        """
        Updates an Elastic IP to point at the new_instance provided.
        """
        return address.associate(InstanceId=new_instance.id)
