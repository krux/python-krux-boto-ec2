# -*- coding: utf-8 -*-
#
# © 2015 Krux Digital, Inc.
#

#
# Standard libraries
#

from __future__ import absolute_import
from pprint import pprint
import re
import time
from decorator import decorator

#
# Third party libraries
#

import boto.ec2
from boto.ec2.blockdevicemapping import BlockDeviceType, BlockDeviceMapping
from retrying import retry

#
# Internal libraries
#

from krux_boto import Boto, add_boto_cli_arguments
from krux.logging import get_logger
from krux.stats import get_stats
from krux.cli import get_parser, get_group
from krux_ec2.filter import Filter


NAME = 'krux-ec2'


@decorator
def map_search_to_filter(f, *args, **kwargs):
    """Replace a search argument with an instance of Filter.

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

    return f(args[0], search_filter)


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

    boto = Boto(
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


class EC2(object):
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
        # Private variables, not to be used outside this module
        self._name = NAME
        self._logger = logger or get_logger(self._name)
        self._stats = stats or get_stats(prefix=self._name)

        # Throw exception when Boto2 is not used
        # TODO: Start using Boto3 and reverse this check
        if not isinstance(boto, Boto):
            raise TypeError('krux_ec2.ec2.EC2 only supports krux_boto.boto.Boto')

        self.boto = boto

        # Set up default cache
        self._conn = None

    def _get_connection(self):
        """
        Returns a connection to the designated region (self.boto.cli_region).
        The connection is established on the first call for this instance (lazy) and cached.
        """
        if self._conn is None:
            self._conn = self.boto.ec2.connect_to_region(self.boto.cli_region)

        return self._conn

    @retry(
        stop_max_delay=TIMEOUT,
        wait_fixed=CHECK_INTERVAL,
        # GOTCHA: Sometimes, the first few checks may be performed when the item is not ready.
        # This causes an error. Ignore this error during this check.
        retry_on_exception=lambda e: isinstance(e, boto.exception.EC2ResponseError),
        retry_on_result=lambda r: not r
    )
    def _wait(self, item, check_func):
        item.update()
        return check_func(item)

    @map_search_to_filter
    def find_instances(self, instance_filter):
        """
        Returns a list of instances that matches the search criteria.

        The search parameter must be either a krux_ec2.filter.Filter instance or
        a dictionary or a list that krux_ec2.filter.Filter class can handle.
        Refer to the docstring on the class.
        """

        self._logger.debug('Filters to use: %s', dict(instance_filter))

        ec2 = self._get_connection()
        instances = ec2.get_only_instances(filters=dict(instance_filter))

        self._logger.info('Found following instances: %s', instances)

        return instances

    def find_instances_by_hostname(self, hostname):
        """
        Helper method for looking up instances by hostname.
        """
        return self.ec2.find_instances({
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
        """
        # OK, so, on larger instances, extra devices only show up if you tell them to associate with a block device.
        # These EBS AMIs don't set this up, so we have to. sdb will always be ephemeral0,
        # which is how we've always done it. If there are more devices, they will get sdc,sdd,sde.
        # NOTE: see mounts.pp in kbase for how-we-deal-with-these.
        block_device_map = BlockDeviceMapping()
        sdb = BlockDeviceType()
        sdc = BlockDeviceType()
        sdd = BlockDeviceType()
        sde = BlockDeviceType()
        sdb.ephemeral_name = 'ephemeral0'
        sdc.ephemeral_name = 'ephemeral1'
        sdd.ephemeral_name = 'ephemeral2'
        sde.ephemeral_name = 'ephemeral3'
        block_device_map['/dev/sdb'] = sdb
        block_device_map['/dev/sdc'] = sdc
        block_device_map['/dev/sdd'] = sdd
        block_device_map['/dev/sde'] = sde
        # TODO: Focus attention during code review

        ec2 = self._get_connection()
        reservation = ec2.run_instances(
            image_id=ami_id,
            instance_type=instance_type,
            user_data=cloud_config,
            security_groups=[sec_group],
            block_device_map=block_device_map,
            instance_profile_name=self.INSTANCE_PROFILE_NAME,
            placement=zone,
        )

        self._logger.debug('Started an instance in following reservation: %s', reservation)
        self._logger.debug('Following instances are running on the reservation: %s', reservation.instances)

        instance = reservation.instances[0]

        self._logger.debug('Waiting for the instance to be ready...')
        self._wait(instance, lambda instance: instance.state == 'running')

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
        volume = None

        ec2 = self._get_connection()
        if volume_id is not None:
            # GOTCHA: volume_id takes priority over volume_size
            volume = ec2.create_volume(volume_ids=[volume_id])[0]
        elif volume_size is not None:
            volume = ec2.create_volume(volume_size, instance.placement)

            self._logger.debug('Waiting for the EBS volume to be ready...')
            self._wait(volume, lambda volume: volume.status == 'available')
        else:
            raise ValueError('Either volume_id or volume_size is required')

        volume.attach(instance.id, device)

        self._logger.debug('Waiting for the EBS volume to be attached...')
        self._wait(volume, lambda volume: volume.attachment_state() == 'attached')

        if not save_on_termination:
            instance.modify_attribute('blockDeviceMapping', {device: True})

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
        """

        self._logger.debug('Filters to use: %s', dict(ebs_filter))

        ec2 = self._get_connection()
        volumes = ec2.get_all_volumes(filters=dict(ebs_filter))

        self._logger.info('Found following volumes: %s', volumes)

        return volumes

    def find_security_group(self, security_group):
        """
        Returns a list of security groups with the given group name.

        Performs a contains search rather than exact match.
        """
        security_filter = Filter()
        security_filter.add_filter('group-name', security_group)

        self._logger.debug('Filters to use: %s', dict(security_filter))

        ec2 = self._get_connection()
        sec_groups = ec2.get_all_security_groups(filters=dict(security_filter))

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
        ec2 = self._get_connection()
        elastic_ips = ec2.get_all_addresses()
        return [ip for ip in elastic_ips if ip.instance_id == instance.id]    

    def update_elastic_ip(ip, new_instance):
        """
        Updates an Elastic IP to point at the new_instance provided.
        """
        ip.disassociate()
        return ip.associate(instance_id=new_instance.id)
