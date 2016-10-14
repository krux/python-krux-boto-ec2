# -*- coding: utf-8 -*-
#
# © 2016 Krux Digital, Inc.
#

#
# Standard libraries
#

from __future__ import absolute_import

#
# Internal libraries
#

import krux_boto.cli
from krux_ec2.ec2 import add_ec2_cli_arguments, get_ec2, NAME
from krux_ec2.filter import Filter


class Application(krux_boto.cli.Application):

    def __init__(self, name=NAME):
        # Call to the superclass to bootstrap.
        super(Application, self).__init__(name=name)

        self.ec2 = get_ec2(self.args, self.logger, self.stats)

    def add_cli_arguments(self, parser):
        # Call to the superclass
        super(Application, self).add_cli_arguments(parser)

        add_ec2_cli_arguments(parser, include_boto_arguments=False)

    def run(self):
        f = Filter({
            'tag:Name': ['cc001.krxd.net'],
            'instance-state-name': ['running', 'stopped'],
        })
        self.ec2.find_instances(f)


def main():
    app = Application()
    with app.context():
        app.run()


# Run the application stand alone
if __name__ == '__main__':
    main()
