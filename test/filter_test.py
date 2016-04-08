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
        dic = {
            'tag:Name': 'example.krxd.net',
            'instance-state-name': ['running', 'stopped']
        }
        self.f = Filter(dic)

        self.assertEqual(dic, self.f._filter)

    def test_init_none(self):

        self.assertEqual({}, self.f._filter)

    def test_add_filter_new(self):
        self.f.add_filter('instance-state-name', 'running')
        self.assertIn('instance-state-name', self.f._filter)
        self.assertEqual(['running'], self.f._filter['instance-state-name'])

    def test_add_filter_existing(self):
        self.f.add_filter('instance-state-name', 'running')
        self.f.add_filter('instance-state-name', 'stopped')
        self.assertIn('instance-state-name', self.f._filter)
        self.assertEqual(['running', 'stopped'], self.f._filter['instance-state-name'])

    def test_add_tag_filter(self):
        self.f.add_tag_filter('Name', 'example.krxd.net')
        self.assertIn('tag:Name', self.f._filter)
        self.assertEqual(['example.krxd.net'], self.f._filter['tag:Name'])

    def test_parse_string_name_value(self):
        self.f.parse_string('instance-state-name=running')
        self.assertIn('instance-state-name', self.f._filter)
        self.assertEqual(['running'], self.f._filter['instance-state-name'])

    def test_parse_string_value(self):
        self.f.parse_string('example.krxd.net')
        self.assertIn('tag-value', self.f._filter)
        self.assertEqual(['example.krxd.net'], self.f._filter['tag-value'])

    def test_iter(self):
        dic = {
            'tag:Name': 'example.krxd.net',
            'instance-state-name': ['running', 'stopped']
        }
        self.f = Filter(dic)

        for name, value in self.f:
            self.assertIn(name, dic)
            self.assertEqual(value, dic[name])
