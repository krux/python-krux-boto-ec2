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
    TEST_TAG_KEY = 'Name'
    TEST_TAG_KEY_FULL = 'tag:' + TEST_TAG_KEY
    TEST_TAG_VALUE = 'example.krxd.net'
    TEST_FILTER_KEY = 'instance-state-name'
    TEST_FILTER_VALUE_1 = 'running'
    TEST_FILTER_VALUE_2 = 'stopped'
    TEST_FILTER_VALUE = [TEST_FILTER_VALUE_1, TEST_FILTER_VALUE_2]
    TEST_FILTER_STR = TEST_FILTER_KEY + '=' + TEST_FILTER_VALUE_1

    def setUp(self):
        self.f = Filter()

    def test_init_dict(self):
        """
        Ensure dict passed to __init__ is initialized.
        """
        dic = {
            self.TEST_TAG_KEY_FULL: [self.TEST_TAG_VALUE],
            self.TEST_FILTER_KEY: self.TEST_FILTER_VALUE,
        }
        self.f = Filter(dic)

        self.assertEqual(dic, self.f)

    def test_init_none(self):
        """
        Ensure that filters are initialized empty.
        """
        self.assertEqual({}, self.f)

    def test_init_keywords(self):
        """
        Ensure that filters can be initialized with keywords.
        """
        dic = {
            self.TEST_TAG_KEY_FULL: [self.TEST_TAG_VALUE],
            self.TEST_FILTER_KEY: self.TEST_FILTER_VALUE,
        }
        self.f = Filter(**dic)

        self.assertEqual(dic, self.f)

    def test_add_filter_new(self):
        """
        Make sure Filter.add_filter mutates filter as expected.
        """
        self.f.add_filter(self.TEST_FILTER_KEY, self.TEST_FILTER_VALUE_1)
        self.assertIn(self.TEST_FILTER_KEY, self.f)
        self.assertEqual([self.TEST_FILTER_VALUE_1], self.f[self.TEST_FILTER_KEY])

    def test_add_filter_existing(self):
        """
        Make sure Filter.add_filter is an append operation.
        """
        self.f.add_filter(self.TEST_FILTER_KEY, self.TEST_FILTER_VALUE_1)
        self.f.add_filter(self.TEST_FILTER_KEY, self.TEST_FILTER_VALUE_2)
        self.assertIn(self.TEST_FILTER_KEY, self.f)
        self.assertEqual(self.TEST_FILTER_VALUE, self.f[self.TEST_FILTER_KEY])

    def test_add_tag_filter(self):
        """
        Make sure Filter.add_tag_filter helper creates the appropriate tag filter.
        """
        self.f.add_tag_filter(self.TEST_TAG_KEY, self.TEST_TAG_VALUE)
        self.assertIn(self.TEST_TAG_KEY_FULL, self.f)
        self.assertEqual([self.TEST_TAG_VALUE], self.f[self.TEST_TAG_KEY_FULL])

    def test_parse_string_name_value(self):
        """
        Make sure Filter.parse_string_name_value parses argument names.
        """
        self.f.parse_string(self.TEST_FILTER_STR)
        self.assertIn(self.TEST_FILTER_KEY, self.f)
        self.assertEqual([self.TEST_FILTER_VALUE_1], self.f[self.TEST_FILTER_KEY])

    def test_parse_string_value(self):
        """
        Make sure Filter.parse_string_name_value parses argument values.
        """
        self.f.parse_string(self.TEST_TAG_VALUE)
        self.assertIn('tag-value', self.f._filter)
        self.assertEqual([self.TEST_TAG_VALUE], self.f._filter['tag-value'])

    def test_set(self):
        """
        Make sure Filter attributes can be set via ['name'] notation
        """
        self.f[self.TEST_FILTER_KEY] = self.TEST_FILTER_VALUE
        self.assertEqual(self.TEST_FILTER_VALUE, self.f[self.TEST_FILTER_KEY])

    def test_del(self):
        """
        Make sure Filter attributes can be deleted via ['name'] notation
        """
        self.f.add_filter(self.TEST_FILTER_KEY, self.TEST_FILTER_VALUE_1)
        del self.f[self.TEST_FILTER_KEY]
        self.assertNotIn(self.TEST_FILTER_KEY, self.f._filter)

    def test_iter(self):
        """
        Make sure Filter attributes can be iterated
        """
        self.f.add_filter(self.TEST_FILTER_KEY, self.TEST_FILTER_VALUE_1)
        self.assertEqual([self.TEST_FILTER_KEY], [key for key in self.f])

    def test_len(self):
        """
        Make sure Filter handles len() properly
        """
        self.f.add_filter(self.TEST_FILTER_KEY, self.TEST_FILTER_VALUE_1)
        self.assertEqual(1, len(self.f))
