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

    .. note::
        This only works on methods that have a signature that is just
        self and the search criteria; it doesn't pass on kwargs and you can't
        mangle args as it's a tuple.

    :param wrapped: Function that is wrapped by this decorator
    :type wrapped: function
    :param args: Ordered arguments of `wrapped`. The 2nd argument is modified as :py:class:`krux_ec2.filter.Filter`.
                 The 3rd argument and forward are discarded.
    :type args: list
    :param kwargs: Keyword arguments of `wrapped`. Discarded completely.
    :type kwargs: dict
    """
    # TODO: Update this to allow other arguments
    search_filter = None
    if isinstance(args[1], list):
        search_filter = Filter()
        for term in args[1]:
            search_filter.parse_string(term)
    elif isinstance(args[1], dict):
        search_filter = Filter(args[1])
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
    # This is the IAM role that the instance is started up with. The bootstrap
    # role is needed so that bootstrap.py can update the instance's tags with
    # its status.
    INSTANCE_PROFILE_NAME = 'bootstrap'

    # OK, so, on larger instances, extra devices only show up if you tell them to associate with a block device.
    # These EBS AMIs don't set this up, so we have to. sdb will always be ephemeral0,
    # which is how we've always done it. If there are more devices, they will get sdc,sdd,sde.
    # NOTE: see mounts.pp in kbase for how-we-deal-with-these.
    DEFAULT_BLOCK_DEVICE_MAP = [{
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

    def __init__(
        self,
        boto,
        logger=None,
        stats=None,
    ):
        """
        Basic init

        :param boto: Boto object to be used as an API library to talk to AWS
        :type boto: krux_boto.boto.Boto3
        :param logger: Logger, recommended to be obtained using krux.cli.Application
        :type logger: logging.Logger
        :param stats: Stats, recommended to be obtained using krux.cli.Application
        :type stats: kruxstatsd.StatsClient
        """
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

        .. note::
            The connection is established on the first call for this instance (lazy) and cached.

        :return: Resource to the designated region
        :rtype: boto3.resource
        """
        if self._resource is None:
            self._resource = self.boto.resource(service_name='ec2', region_name=self.boto.cli_region)

        return self._resource

    def _get_client(self):
        """
        Returns a client to the designated region (self.boto.cli_region).

        .. note::
            The connection is established on the first call for this instance (lazy) and cached.

        :return: Client to the designated region
        :rtype: boto3.client
        """
        if self._client is None:
            self._client = self.boto.client(service_name='ec2', region_name=self.boto.cli_region)

        return self._client

    @map_search_to_filter
    def find_instances(self, instance_filter, *args, **kwargs):
        """
        Returns a list of instances that matches the search criteria.

        .. seealso::
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ServiceResource.instances
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#instance

        :param instance_filter: The parameter to search by. Refer to the docstring on the :py:class:`Filter` class for more.
        :type instance_filter: krux_ec2.filter.Filter | dict | list
        :param args: Ordered arguments passed directly to boto3.resource.instances.filter()
        :type args: list
        :param kwargs: Keyword arguments passed directly to boto3.resource.instances.filter()
        :type kwargs: dict
        :return: List of instances that match the search criteria
        :rtype: list[boto3.ec2.Instance]
        """

        self._logger.debug('Filters to use: %s', dict(instance_filter))

        instances = list(self._get_resource().instances.filter(
            Filters=instance_filter.to_filter(),
            *args,
            **kwargs
        ))

        self._logger.info('Found following instances: %s', instances)

        return instances

    def find_instances_by_hostname(self, hostname, *args, **kwargs):
        """
        Helper method for looking up instances by hostname.

        .. seealso::
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ServiceResource.instances
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#instance

        :param hostname: The hostname to look for
        :type hostname: str
        :param args: Ordered arguments passed directly to boto3.resource.instances.filter()
        :type args: list
        :param kwargs: Keyword arguments passed directly to boto3.resource.instances.filter()
        :type kwargs: dict
        :return: List of instances with the given hostname
        :rtype: list[boto3.ec2.Instance]
        """
        return self.find_instances({
            'tag:Name': [hostname],
            'instance-state-name': ['running', 'stopped'],
        })

    def run_instance(
        self,
        ami_id,
        cloud_config,
        instance_type,
        sec_group,
        zone,
        block_device_mappings=DEFAULT_BLOCK_DEVICE_MAP,
        *args,
        **kwargs
    ):
        """
        Starts an instance in the given AMI.

        .. seealso::
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ServiceResource.create_instances
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#instance

        :param ami_id: ID of the AMI image where the new instance will be created
        :type ami_id: str
        :param cloud_config: User data of the new instance
        :type cloud_config: str
        :param instance_type: Instance type of the new instance
        :type instance_type: str
        :param sec_group: Name of the security group the new instance
        :type sec_group: str
        :param zone: Availability zone of the new instance
        :type zone: str
        :param block_device_mappings: Block device mapping of the new instance
        :type block_device_mappings: list[dict]
        :param args: Ordered arguments passed directly to boto3.resource.create_instances()
        :type args: list
        :param kwargs: Keyword arguments passed directly to boto3.resource.create_instances()
        :type kwargs: dict
        :return: The newly created instance
        :rtype: boto3.ec2.Instance
        """
        resource = self._get_resource()
        instances = resource.create_instances(
            ImageId=ami_id,
            MinCount=1,
            MaxCount=1,
            InstanceType=instance_type,
            UserData=cloud_config,
            SecurityGroups=[sec_group],
            BlockDeviceMappings=block_device_mappings,
            IamInstanceProfile={'Name': self.INSTANCE_PROFILE_NAME},
            Placement={'AvailabilityZone': zone},
        )

        instance = instances[0]
        self._logger.debug('Waiting for the instance %s to be ready...', instance.id)

        instance.wait_until_running()
        instance.reload()

        self._logger.info('Started instance %s', instance.public_dns_name)

        return instance

    @staticmethod
    def get_tags(instance_tags):
        """
        Converts the given list of tags into a single dictionary. If there is any duplicate of keys,
        the later overwrites the former.

        :param instance_tags: List of tags
        :type instance_tags: list[dict] | list[EC2.Tag]
        :return: Dictionary of tags
        :rtype: dict
        """
        result = {}
        for tag in instance_tags:
            if isinstance(tag, dict) and 'Key' in tag and 'Value' in tag:
                # GOTCHA: This will throw an error if there is no 'Key' or 'Value' in the dictionary.
                #         That is intentional so that the stacktrace will come back to here.
                key = tag['Key']
                value = tag['Value']
            elif hasattr(tag, 'key') and hasattr(tag, 'value'):
                key = tag.key
                value = tag.value
            else:
                raise ValueError('The {tag} is invalid and/or contains invalid values'.format(tag=tag))

            if key == 's_classes':
                value = value.split(',')

            result[key] = value

        return result

    def attach_ebs_volume(
        self,
        instance,
        device,
        type,
        save_on_termination,
        volume_id=None,
        volume_size=None,
    ):
        """
        Attach a designated EBS volume to the given instance at the given device.

        .. seealso::
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ServiceResource.create_volume
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#volume
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.Volume.attach_to_instance

        :param instance: Instance to which the EBS volume will be attached to
        :type instance: boto3.ec2.Instance
        :param device: Device on the instance to which the EBS volume will be attached to (e.g. /dev/sdf)
        :type device: str
        :param type: Type of the EBS volume to be attached
        :type type: str
        :param save_on_termination: Whether to keep the volume even after the instance is terminated
        :type save_on_termination: bool
        :param volume_id: ID of a specific volume to use. If set to none, a new volume with the size of `volume_size`
                          will be created and used.
        :type volume_id: str
        :param volume_size: Size of a new volume to create. If `volume_id` and `volume_size` are both None, an error
                            is raised.
        :type volume_size: int
        :return: The newly attached EBS volume
        :rtype: boto3.ec2.Volume
        """
        if volume_id is not None:
            # GOTCHA: volume_id takes priority over volume_size
            volume = self.find_ebs_volumes({'volume-id': [volume_id]})[0]
        elif volume_size is not None:
            volume = self._get_resource().create_volume(
                Size=volume_size,
                AvailabilityZone=instance.placement['AvailabilityZone'],
                VolumeType=type,
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
    def find_ebs_volumes(self, ebs_filter, *args, **kwargs):
        """
        Returns a list of EBS volumes that matches the search criteria.

        .. seealso::
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ServiceResource.volumes
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#volume

        :param ebs_filter: The parameter to search by. Refer to the docstring on the :py:class:`Filter` class for more.
        :type ebs_filter: krux_ec2.filter.Filter | dict | list
        :param args: Ordered arguments passed directly to boto3.resource.volume.filter()
        :type args: list
        :param kwargs: Keyword arguments passed directly to boto3.resource.volume.filter()
        :type kwargs: dict
        :return: List of EBS volumes that match the search criteria
        :rtype: list[boto3.ec2.Volume]
        """

        self._logger.debug('Filters to use: %s', dict(ebs_filter))

        volumes = list(self._get_resource().volumes.filter(
            Filters=ebs_filter.to_filter(),
            *args,
            **kwargs
        ))

        self._logger.info('Found following volumes: %s', volumes)

        return volumes

    def find_security_group(self, security_group, *args, **kwargs):
        """
        Returns a list of security groups with the given group name.

        Performs a contains search rather than exact match.

        .. seealso::
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ServiceResource.security_groups
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#securitygroup

        :param security_group: The name of the security group to search for
        :type security_group: str
        :param args: Ordered arguments passed directly to boto3.resource.security_groups.filter()
        :type args: list
        :param kwargs: Keyword arguments passed directly to boto3.resource.security_groups.filter()
        :type kwargs: dict
        :return: List of security groups that match the search criteria
        :rtype: list[boto3.ec2.SecurityGroup]
        """
        security_filter = Filter()
        security_filter.add_filter('group-name', security_group)

        self._logger.debug('Filters to use: %s', dict(security_filter))

        sec_groups = list(self._get_resource().security_groups.filter(
            Filters=security_filter.to_filter(),
            *args,
            **kwargs
        ))

        self._logger.info('Found following security groups: %s', sec_groups)

        return sec_groups

    def find_elastic_ip(self, ip, *args, **kwargs):
        """
        Find the Elastic IP(s) mapped to a given instance.

        .. seealso::
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.Instance.classic_address
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#classicaddress

        .. note::
            Please note that VPC supports up to 30 IPs per host, which means you
            will not always get a single IP back.

        .. deprecated:: 0.1.0
            Use `instance.classic_address` instead

        :param ip: The public IP of the Elastic IP to search for
        :type ip: str
        :param args: Ordered arguments passed directly to boto3.resource.classic_addresses.filter()
        :type args: list
        :param kwargs: Keyword arguments passed directly to boto3.resource.classic_addresses.filter()
        :type kwargs: dict
        :return: List of elastic IPs for the given instance
        :rtype: list[boto3.ec2.ClassicAddress]
        """
        # GOTCHA: Do not use PublicIps parameter here by default because it will cause an exception when
        #         used with a non-existing IP. Allow users to enter any IPs and return them an empty list
        #         if no EIP matches it.
        return [
            classic_address for classic_address in self._get_resource().classic_addresses.filter(*args, **kwargs)
            if classic_address.public_ip == ip
        ]

    def update_elastic_ip(self, instance, address):
        """
        Updates an Elastic IP to point at the new_instance provided.

        .. seealso::
            https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ClassicAddress.associate

        :param instance: Instance to be associated with the given elastic IP
        :type instance: boto3.ec2.Instance
        :param address: Elastic IP to update or None to disassociate the elastic IP
        :type address: boto3.ec2.ClassicAddress | None
        """
        if address is not None:
            address.associate(InstanceId=instance.id)
        else:
            for classic_address in self.find_elastic_ip(instance.classic_address.public_ip):
                classic_address.disassociate()
