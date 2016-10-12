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
# Internal libraries
#

from krux_ec2.filter import Filter


class FilterTest(unittest.TestCase):
    """
    Test case for Filter
    """

    def setUp(self):
        self.f = Filter()

    def test_init_dict(self):
        """
        Ensure dict passed to __init__ is initialized.
        """
        dic = {
            'tag:Name': ['example.krxd.net'],
            'instance-state-name': ['running', 'stopped']
        }
        self.f = Filter(dic)

        self.assertEqual(dic, self.f._filter)

    def test_init_none(self):
        """
        Ensure that filters are initialized empty.
        """
        self.assertEqual({}, self.f._filter)

    def test_add_filter_new(self):
        """
        Make sure Filter.add_filter mutates filter as expected.
        """
        self.f.add_filter('instance-state-name', 'running')
        self.assertIn('instance-state-name', self.f._filter)
        self.assertEqual(['running'], self.f._filter['instance-state-name'])

    def test_add_filter_existing(self):
        """
        Make sure Filter.add_filter is an append operation.
        """
        self.f.add_filter('instance-state-name', 'running')
        self.f.add_filter('instance-state-name', 'stopped')
        self.assertIn('instance-state-name', self.f._filter)
        self.assertEqual(['running', 'stopped'], self.f._filter['instance-state-name'])

    def test_add_tag_filter(self):
        """
        Make sure Filter.add_tag_filter helper creates the appropriate tag filter.
        """
        self.f.add_tag_filter('Name', 'example.krxd.net')
        self.assertIn('tag:Name', self.f._filter)
        self.assertEqual(['example.krxd.net'], self.f._filter['tag:Name'])

    def test_parse_string_name_value(self):
        """
        Make sure Filter.parse_string_name_value parses argument names.
        """
        self.f.parse_string('instance-state-name=running')
        self.assertIn('instance-state-name', self.f._filter)
        self.assertEqual(['running'], self.f._filter['instance-state-name'])

    def test_parse_string_value(self):
        """
        Make sure Filter.parse_string_name_value parses argument values.
        """
        self.f.parse_string('example.krxd.net')
        self.assertIn('tag-value', self.f._filter)
        self.assertEqual(['example.krxd.net'], self.f._filter['tag-value'])

    def test_get(self):
        """
        Make sure Filter attributes are accessible via ['name'] notation
        """
        self.f.add_filter('instance-state-name', 'running')
        self.assertEqual(['running'], self.f['instance-state-name'])

    def test_set(self):
        """
        Make sure Filter attributes can be set via ['name'] notation
        """
        self.f['instance-state-name'] = ['running']
        self.assertEqual(['running'], self.f['instance-state-name'])

    def test_del(self):
        """
        Make sure Filter attributes can be deleted via ['name'] notation
        """
        self.f.add_filter('instance-state-name', 'running')
        del self.f['instance-state-name']
        self.assertNotIn('instance-state-name', self.f._filter)

    def test_iter(self):
        """
        Make sure Filter attributes can be iterated
        """
        self.f.add_filter('instance-state-name', 'running')
        self.assertEqual(['instance-state-name'], [key for key in self.f])

    def test_len(self):
        """
        Make sure Filter handles len() properly
        """
        self.f.add_filter('instance-state-name', 'running')
        self.assertEqual(1, len(self.f))
