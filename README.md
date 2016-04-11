# krux_ec2

`krux_ec2` is a library that provides wrapper functions for common EC2 usage. It uses `krux_boto` to connect to AWS EC2.

## Warning

In the current version, `krux_ec2.ec2.EC2` is only compatible with `krux_boto.boto.Boto` object. Passing other objects, such as `krux_boto.boto.Boto3`, will cause an exception.

## Application quick start

The most common use case is to build a CLI script using `krux_ec2.cli.Application`.
Here's how to do that:

```python

import krux_ec2.cli
from krux_ec2.filter import Filter

# This class inherits from krux.cli.Application, so it provides
# all that functionality as well.
class Application(krux_ec2.cli.Application):
    def run(self):
        f = Filter({
            'tag:Name': 'example.krxd.net',
            'instance-state-name': ['running', 'stopped'],
        })
        print self.ec2.find_instances(f)

def main():
    # The name must be unique to the organization.
    app = Application(name='krux-my-ec2-script')
    with app.context():
        app.run()

# Run the application stand alone
if __name__ == '__main__':
    main()

```

## Extending your application

From other CLI applications, you can make the use of `krux_ec2.ec2.get_ec2()` function.

```python

from krux_ec2.ec2 import add_ec2_cli_arguments, get_ec2
import krux.cli

class Application(krux.cli.Application):

    def __init__(self, *args, **kwargs):
        super(Application, self).__init__(*args, **kwargs)

        self.ec2 = get_ec2(self.args, self.logger, self.stats)

    def add_cli_arguments(self, parser):
        super(Application, self).add_cli_arguments(parser)

        add_ec2_cli_arguments(parser)

```

Alternately, you want to add S3 functionality to your larger script or application.
Here's how to do that:

```python

from krux_boto import Boto
from krux_ec2.ec2 import EC2
from krux_ec2.filter import Filter

class MyApplication(object):

    def __init__(self, *args, **kwargs):
        boto = Boto(
            logger=self.logger,
            stats=self.stats,
        )
        self.ec2 = EC2(
            boto=boto,
            logger=self.logger,
            stats=self.stats,
        )

    def run(self):
        f = Filter({
            'tag:Name': 'example.krxd.net',
            'instance-state-name': ['running', 'stopped'],
        })
        print self.ec2.find_instances(f)

```

As long as you get an instance of `krux_boto.boto.Boto`, the rest are the same. Refer to `krux_boto` module's [README](https://github.com/krux/python-krux-boto/blob/master/README.md) on various ways to instanciate the class.
