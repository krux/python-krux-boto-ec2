import unittest
import mock

from krux_ec2.ec2 import EC2, map_search_to_filter
from krux_ec2.filter import Filter
from krux_boto import Boto


class EC2Tests(unittest.TestCase):
    """EC2 class"""
    def test_find_elastic_ips_returns_empty_list(self):
        """Ensure empty lists are sent when no IPs match."""
        mocked_boto = Boto()

        ec2 = EC2(mocked_boto, mock.MagicMock(), mock.MagicMock())

        address1 = mock.Mock()
        address1.instance_id = 'address1'

        address2 = mock.Mock()
        address2.instance_id = 'address2'

        mocked_ec2 = mock.Mock()
        mocked_ec2.get_all_addresses = mock.Mock(return_value=[
            address1, address2
        ])

        ec2._get_connection = mock.Mock(return_value=mocked_ec2)

        instance = mock.Mock()
        instance.id = 'not-me'

        self.assertEqual([], ec2.find_elastic_ips(instance)) 


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
        self.assertEqual(['running'],
            self.search_stub.results._filter['instance-state-name'])

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
            self.search_stub.filter_stubs(mock.Mock())
