# -*- coding: utf-8 -*-
#
# © 2015 Krux Digital, Inc.
#

#
# Standard libraries
#

from __future__ import absolute_import
from collections import MutableMapping

#
# Third party libraries
#

from six import iteritems


class Filter(MutableMapping):
    """
    Class to represent and handle AWS API's filters.

    .. seealso:: https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ServiceResource.instances

    :example:
    You can use this in 3 different ways:
        1. Pass a dictionary of filter criteria and values to the constructor
        2. Create an empty filter and add criteria using add_filter or add_tag_filter methods
        3. Create an empty filter and add creteria from string using parse_string method

    >>> f1 = Filter({'tag:Name': ['example.krxd.net'], 'instance-state-name': ['running', 'stopped']})

    >>> f2 = Filter()
    >>> f2.add_tag_filter('Name', 'example.krxd.net')
    >>> f2.add_filter('instance-state-name', 'running')
    >>> f2.add_filter('instance-state-name', 'stopped')

    >>> f3 = Filter()
    >>> f3.parse_string('tag:Name=example.krxd.net')
    >>> f3.parse_string('instance-state-name=running')
    >>> f3.parse_string('instance-state-name=stopped')

    All 3 above filters return a list of items that have 'example.krxd.net' value for the 'Name' tag
    AND is either 'running' OR 'stopped'.
    """

    def __init__(self, initial=None):
        """
        The initial parameter must be a dictionary of string to a list of values.
        The key is the filter criteria name, and the value is a list of matches.

        :param initial: Initial set of filters to start with
        :type initial: dict | None
        """
        self._filter = {}

        if initial is not None:
            self._filter.update(initial)

    def __getitem__(self, key):
        return self._filter[key]

    def __setitem__(self, key, value):
        self._filter[key] = value

    def __delitem__(self, key):
        del self._filter[key]

    def __iter__(self):
        return iter(self._filter)

    def __len__(self):
        return len(self._filter)

    def add_filter(self, name, value):
        """
        Adds a filter with the given criteria name and value.
        If there exists a filter with the given criteria, the value is added to the potential match,
        creating an OR match.

        For filtering via tags, use add_tag_filter.

        .. seealso:: https://boto3.readthedocs.io/en/stable/reference/services/ec2.html#EC2.ServiceResource.instances

        :param name: Name of the filter (e.g. 'instance-type')
        :type name: str
        :param value: Value of the filter (e.g. 'c3.large')
        :type value: str
        """
        if name in self:
            self[name].append(value)
        else:
            self.update({name: [value]})

    def add_tag_filter(self, name, value):
        """
        Adds a filter with the given tag name and value.

        .. seealso:: Filter.add_filter()

        :param name: Name of the tag (e.g. 'krux-status')
        :type name: str
        :param value: Value of the filter (e.g. 'bootstrap_complete')
        :type value: str
        """
        self.add_filter('tag:{0}'.format(name), value)

    def parse_string(self, search_term):
        """
        Parses the given string to create a filter.

        The string must follow the format "key=value". If "=" is not present in the string,
        the string is considered as a "tag-value" search. For searching tags, use "tag:Key=value" format.

        :param search_term: A string containing the key and the value of search filter with `=` as the delimiter.
        :type search_term: str
        """
        if '=' in search_term:
            name, value = search_term.split('=', 1)
        else:
            name = 'tag-value'
            value = search_term

        self.add_filter(name, value)

    def to_filter(self):
        """
        Override so that dict(Filter) returns the dict to be used by boto.
        """
        return [
            {'Name': key, 'Values': values}
            for key, values in iteritems(self)
        ]
