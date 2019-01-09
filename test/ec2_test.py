# -*- coding: utf-8 -*-
#
# © 2015 Krux Digital, Inc.
#

#
# Standard libraries
#

from __future__ import absolute_import
import unittest

#
# Third party libraries
#

from mock import MagicMock, patch, call
from six import iteritems

#
# Internal libraries
#

from krux_ec2.ec2 import EC2, map_search_to_filter
from krux_ec2.filter import Filter
from krux_boto import Boto


class EC2Tests(unittest.TestCase):
    FAKE_HOSTNAME = 'example.krxd.net'
    FAKE_AMI_ID = 'ami-a1b2c3d4'
    FAKE_CLOUD_CONFIG = '#cloud_config'
    FAKE_INSTANCE_TYPE = 'c3.large'
    FAKE_SECURITY_GROUP = 'krux-security-group'
    FAKE_ZONE = 'us-east-1a'
    FAKE_DEVICE = '/dev/sdz'
    FAKE_VOLUME_SIZE = 10
    FAKE_ADDRESS = '127.0.0.1'
    FAKE_ELASTIC_IP = MagicMock(public_ip=FAKE_ADDRESS)
    FAKE_VOLUME_TYPE = 'gp2'
    FAKE_INSTANCE = MagicMock(
        id='i-a1b2c3d4',
        public_dns_name='ec2-127-0-0-1.compute-1.amazonaws.com',
        placement={
            'AvailabilityZone': FAKE_ZONE,
        },
        classic_address=FAKE_ELASTIC_IP
    )
    FAKE_VOLUME = MagicMock(
        id='vol-a1b2c3d4',
    )
    FAKE_TAGS = {
        'Name': FAKE_HOSTNAME,
        's_classes': ['s_basic', 's_basic::minimal'],
    }
    FAKE_TAGS_DICT = [
        {'Key': key, 'Value': ','.join(value) if isinstance(value, list) else value}
        for key, value in iteritems(FAKE_TAGS)
    ]
    FAKE_TAGS_TAG = [
        MagicMock(key=key, value=(','.join(value) if isinstance(value, list) else value))
        for key, value in iteritems(FAKE_TAGS)
    ]

    _BLOCK_DEVICE_MAP = [{
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
    _INSTANCE_PROFILE_NAME = 'bootstrap'

    def setUp(self):
        self._logger = MagicMock()
        self._stats = MagicMock()

        self._boto = MagicMock()
        self._resource = self._boto.resource.return_value

        self.FAKE_INSTANCE.reset_mock()
        self.FAKE_VOLUME.reset_mock()

        with patch('krux_ec2.ec2.isinstance', return_value=True):
            self._ec2 = EC2(
                boto=self._boto,
                logger=self._logger,
                stats=self._stats
            )

    def test_init(self):
        """
        EC2.__init__() correctly sets up all properties
        """
        self.assertEqual(self._boto, self._ec2.boto)
        self.assertIsNone(self._ec2._resource)
        self.assertIsNone(self._ec2._client)

    def test_get_resource(self):
        """
        EC2._get_resource() correctly returns a resource object
        """
        resource = self._ec2._get_resource()

        self.assertEqual(self._resource, resource)
        self._boto.resource.assert_called_once_with(
            service_name='ec2',
            region_name=self._boto.cli_region
        )

    def test_get_resource_cached(self):
        """
        EC2._get_resource() correctly uses the cached value when available
        """
        expected = MagicMock()
        self._ec2._resource = expected
        actual = self._ec2._get_resource()

        self.assertEqual(expected, actual)
        self.assertFalse(self._boto.resource.called)

    def test_find_instances(self):
        """
        EC2.find_instances correctly locate instances based on search criteria
        """
        filter = Filter()

        expected = [self.FAKE_INSTANCE]
        self._resource.instances.filter.return_value = expected
        actual = self._ec2.find_instances(filter)

        self.assertEqual(expected, actual)
        self._logger.debug.assert_called_once_with(
            'Filters to use: %s', dict(filter)
        )
        self._logger.info.assert_called_once_with(
            'Found following instances: %s', expected
        )

    def test_find_instances_by_hostname(self):
        """
        EC2.find_instances_by_hostname correctly locate instances based hostname.
        """
        filter = Filter()
        filter.add_filter('instance-state-name', 'running')
        filter.add_filter('instance-state-name', 'stopped')
        filter.add_tag_filter('Name', self.FAKE_HOSTNAME)

        self._ec2.find_instances_by_hostname(self.FAKE_HOSTNAME)

        self._logger.debug.assert_called_once_with(
            'Filters to use: %s', dict(filter)
        )

    def test_run_instance(self):
        """
        EC2.run_instance correctly starts an instance
        """
        self._resource.create_instances.return_value = [self.FAKE_INSTANCE]

        instance = self._ec2.run_instance(
            ami_id=self.FAKE_AMI_ID,
            cloud_config=self.FAKE_CLOUD_CONFIG,
            instance_type=self.FAKE_INSTANCE_TYPE,
            sec_group=self.FAKE_SECURITY_GROUP,
            zone=self.FAKE_ZONE,
        )

        self.assertEqual(self.FAKE_INSTANCE, instance)
        self._resource.create_instances.assert_called_once_with(
            ImageId=self.FAKE_AMI_ID,
            MinCount=1,
            MaxCount=1,
            InstanceType=self.FAKE_INSTANCE_TYPE,
            UserData=self.FAKE_CLOUD_CONFIG,
            SecurityGroups=[self.FAKE_SECURITY_GROUP],
            BlockDeviceMappings=self._BLOCK_DEVICE_MAP,
            IamInstanceProfile={'Name': self._INSTANCE_PROFILE_NAME},
            Placement={'AvailabilityZone': self.FAKE_ZONE},
        )
        self._logger.debug.assert_called_once_with(
            'Waiting for the instance %s to be ready...', self.FAKE_INSTANCE.id
        )
        self.FAKE_INSTANCE.reload.assert_called_once_with()
        self._logger.info.assert_called_once_with(
            'Started instance %s', self.FAKE_INSTANCE.public_dns_name
        )

    def test_run_instance_with_custom_profile(self):
        """
        EC2.run_instance correctly starts an instance with a custom IAM Instance Profile
        """
        self._resource.create_instances.return_value = [self.FAKE_INSTANCE]

        instance = self._ec2.run_instance(
            ami_id=self.FAKE_AMI_ID,
            cloud_config=self.FAKE_CLOUD_CONFIG,
            instance_type=self.FAKE_INSTANCE_TYPE,
            sec_group=self.FAKE_SECURITY_GROUP,
            zone=self.FAKE_ZONE,
            iam_instance_profile='FakeProfile',
        )

        self.assertEqual(self.FAKE_INSTANCE, instance)
        self._resource.create_instances.assert_called_once_with(
            ImageId=self.FAKE_AMI_ID,
            MinCount=1,
            MaxCount=1,
            InstanceType=self.FAKE_INSTANCE_TYPE,
            UserData=self.FAKE_CLOUD_CONFIG,
            SecurityGroups=[self.FAKE_SECURITY_GROUP],
            BlockDeviceMappings=self._BLOCK_DEVICE_MAP,
            IamInstanceProfile={'Name': 'FakeProfile'},
            Placement={'AvailabilityZone': self.FAKE_ZONE},
        )
        self._logger.debug.assert_called_once_with(
            'Waiting for the instance %s to be ready...', self.FAKE_INSTANCE.id
        )
        self.FAKE_INSTANCE.reload.assert_called_once_with()
        self._logger.info.assert_called_once_with(
            'Started instance %s', self.FAKE_INSTANCE.public_dns_name
        )


    def test_get_tags_dict(self):
        """
        EC2.get_tags correctly converts the tags in list[dict] format
        """
        result = EC2.get_tags(self.FAKE_TAGS_DICT)
        self.assertEqual(self.FAKE_TAGS, result)

    def test_get_tags_tags(self):
        """
        EC2.get_tags correctly converts the tags in list[EC2.Tag] format
        """
        result = EC2.get_tags(self.FAKE_TAGS_TAG)
        self.assertEqual(self.FAKE_TAGS, result)

    def test_get_tags_dict_no_key(self):
        """
        EC2.get_tags correctly raises error when no 'Key' key is present in a dictionary
        """
        invalid_tag = {'Value': 'foo'}
        with self.assertRaises(ValueError) as e:
            EC2.get_tags([invalid_tag])

        self.assertEqual(
            'The {tag} is invalid and/or contains invalid values'.format(tag=invalid_tag),
            str(e.exception),
        )

    def test_get_tags_dict_no_value(self):
        """
        EC2.get_tags correctly raises error when no 'Value' key is present in a dictionary
        """
        invalid_tag = {'Key': 'foo'}
        with self.assertRaises(ValueError) as e:
            EC2.get_tags([invalid_tag])

        self.assertEqual(
            'The {tag} is invalid and/or contains invalid values'.format(tag=invalid_tag),
            str(e.exception),
        )

    def test_get_tags_wrong_type(self):
        """
        EC2.get_tags correctly raises error when wrong typed tag is passed
        """
        invalid_tag = 1
        with self.assertRaises(ValueError) as e:
            EC2.get_tags([invalid_tag])

        self.assertEqual(
            'The {tag} is invalid and/or contains invalid values'.format(tag=invalid_tag),
            str(e.exception),
        )

    def test_attach_ebs_volume(self):
        """
        EC2.attach_ebs_volume correctly creates a volume with the matching size and attach it to an instance
        """
        self._resource.create_volume.return_value = self.FAKE_VOLUME

        volume = self._ec2.attach_ebs_volume(
            device=self.FAKE_DEVICE,
            instance=self.FAKE_INSTANCE,
            save_on_termination=False,
            volume_size=self.FAKE_VOLUME_SIZE,
            volume_type=self.FAKE_VOLUME_TYPE,
        )

        self.assertEqual(self.FAKE_VOLUME, volume)

        self._resource.create_volume.assert_called_once_with(
            Size=self.FAKE_VOLUME_SIZE,
            AvailabilityZone=self.FAKE_ZONE,
            VolumeType=self.FAKE_VOLUME_TYPE,
        )
        self.FAKE_VOLUME.reload.assert_called_once_with()
        self.FAKE_VOLUME.attach_to_instance.assert_called_once_with(
            InstanceId=self.FAKE_INSTANCE.id,
            Device=self.FAKE_DEVICE,
        )
        self.FAKE_INSTANCE.modify_attribute.assert_called_once_with(BlockDeviceMappings=[{
            'DeviceName': self.FAKE_DEVICE,
            'Ebs': {
                'VolumeId': self.FAKE_VOLUME.id,
                'DeleteOnTermination': True,
            },
        }])

        debug_calls = [
            call('Waiting for the EBS volume %s to be ready...', self.FAKE_VOLUME.id),
            call('Waiting for the EBS volume to be attached...')
        ]
        self.assertEqual(debug_calls, self._logger.debug.call_args_list)
        self._logger.info.assert_called_once_with(
            'Attached EBS volume %s to instance %s at %s',
            self.FAKE_VOLUME.id, self.FAKE_INSTANCE.public_dns_name, self.FAKE_DEVICE,
        )

    def test_attach_ebs_volume_id(self):
        """
        EC2.attach_ebs_volume correctly attach an EBS volume to an instance when given the ID
        """
        filter = Filter()
        filter.add_filter('volume-id', self.FAKE_VOLUME.id)
        self._resource.volumes.filter.return_value = [self.FAKE_VOLUME]

        volume = self._ec2.attach_ebs_volume(
            device=self.FAKE_DEVICE,
            instance=self.FAKE_INSTANCE,
            save_on_termination=False,
            volume_id=self.FAKE_VOLUME.id,
        )

        self.assertEqual(self.FAKE_VOLUME, volume)

        self.assertFalse(self.FAKE_VOLUME.reload.called)

        debug_calls = [
            call('Filters to use: %s', dict(filter)),
            call('Waiting for the EBS volume to be attached...'),
        ]
        self.assertEqual(debug_calls, self._logger.debug.call_args_list)

    def test_attach_ebs_volume_save_on_termination(self):
        """
        EC2.attach_ebs_volume correctly designates the EBS volume to be saved when needed
        """
        self._resource.create_volume.return_value = self.FAKE_VOLUME

        self._ec2.attach_ebs_volume(
            device=self.FAKE_DEVICE,
            instance=self.FAKE_INSTANCE,
            save_on_termination=True,
            volume_size=self.FAKE_VOLUME_SIZE,
            volume_type=self.FAKE_VOLUME_TYPE,
        )

        self.FAKE_INSTANCE.modify_attribute.assert_called_once_with(BlockDeviceMappings=[{
            'DeviceName': self.FAKE_DEVICE,
            'Ebs': {
                'VolumeId': self.FAKE_VOLUME.id,
                'DeleteOnTermination': False,
            },
        }])

    def test_attach_ebs_volume_no_args(self):
        """
        EC2.attach_ebs_volume correctly throws an error when neither volume_id or volume_size is provided
        """
        with self.assertRaises(ValueError) as e:
            self._ec2.attach_ebs_volume(
                device=self.FAKE_DEVICE,
                instance=self.FAKE_INSTANCE,
                save_on_termination=False,
            )

        self.assertEqual('Either volume_id or volume_size is required', str(e.exception))

    def test_find_ebs_volumes(self):
        """
        EC2.find_ebs_volumes correctly locate EBS volumes based on search criteria
        """
        filter = Filter()

        expected = [self.FAKE_VOLUME]
        self._resource.volumes.filter.return_value = expected
        actual = self._ec2.find_ebs_volumes(filter)

        self.assertEqual(expected, actual)
        self._logger.debug.assert_called_once_with(
            'Filters to use: %s', dict(filter)
        )
        self._logger.info.assert_called_once_with(
            'Found following volumes: %s', expected
        )

    def test_find_elastic_ips(self):
        """
        EC2.find_elastic_ips correctly returns the elastic IP of the instance
        """
        self._resource.classic_addresses.filter.return_value = [
            self.FAKE_ELASTIC_IP,
            MagicMock(public_ip='196.168.0.1'),
        ]

        self.assertEqual([self.FAKE_ELASTIC_IP], self._ec2.find_elastic_ip(self.FAKE_ADDRESS))

    def test_find_elastic_ips_none(self):
        """
        EC2.find_elastic_ips correctly returns an empty list if a non-existing IP is given
        """
        self._resource.classic_addresses.filter.return_value = [
            self.FAKE_ELASTIC_IP,
            MagicMock(public_ip='196.168.0.1'),
        ]

        self.assertEqual([], self._ec2.find_elastic_ip('255.255.255.255'))

    def test_update_elastic_ip_new(self):
        """
        EC2.update_elastic_ip correctly associates the elastic IP to the new instance
        """
        address = MagicMock()

        self._ec2.update_elastic_ip(self.FAKE_INSTANCE, address)

        address.associate.assert_called_once_with(InstanceId=self.FAKE_INSTANCE.id)

    def test_update_elastic_ip_delete(self):
        """
        EC2.update_elastic_ip correctly disassociates all elastic IPs for an instance if None is passed
        """
        self._resource.classic_addresses.filter.return_value = [self.FAKE_ELASTIC_IP]

        self._ec2.update_elastic_ip(self.FAKE_INSTANCE, None)

        self.FAKE_ELASTIC_IP.disassociate.assert_called_once_with()


class MapSearchToFilterStub(object):
    """Used below to test the @map_search_to_filter decorator."""
    @map_search_to_filter
    def filter_stubs(self, search):
        self.results = search


class MapSearchToFilterDecoratorTests(unittest.TestCase):
    def setUp(self):
        self.search_stub = MapSearchToFilterStub()

    def test_map_search_to_filter_passes_filter_without_modification(self):
        """Ensure passing an instance of Filter is not mutated."""
        my_filter = Filter({'instance-state-name': ['running']})
        self.search_stub.filter_stubs(my_filter)
        self.assertEqual(my_filter, self.search_stub.results)

    def test_map_search_to_filter_handles_a_list(self):
        """Ensure a list of arg=val pairs is parsed correctly."""
        search = ['instance-state-name=running']
        self.search_stub.filter_stubs(search)
        self.assertEqual(
            ['running'],
            self.search_stub.results._filter['instance-state-name']
        )

    def test_map_search_to_filter_handles_dict(self):
        """Ensure instance of Filter is instantiated with dict passed."""
        my_filter = {
            'instance-state-name': ['running']
        }

        self.search_stub.filter_stubs(my_filter)
        self.assertEqual(my_filter, self.search_stub.results._filter)

    def test_invalid_argument_raises_error(self):
        """Make sure NotImplementedError is raised on invalid arguments."""
        with self.assertRaises(NotImplementedError):
            self.search_stub.filter_stubs(MagicMock())
