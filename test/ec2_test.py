import unittest
import mock

from krux_ec2.ec2 import EC2
from krux_boto import Boto


class EC2Test(unittest.TestCase):
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
