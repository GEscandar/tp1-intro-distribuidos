import click
import functools


def common_options(host=True):
    options = [
        click.option(
            "-v",
            "--verbose",
            is_flag=True,
            help=("Emit messages about ongoing file transfer operations"),
        ),
        click.option(
            "-q",
            "--quiet",
            is_flag=True,
            help=("decrease output verbosity"),
        ),
    ]
    if host:
        options.append(
            click.option(
                "-H",
                "--host",
                help=("server IP address"),
            )
        )
    options.append(
        click.option(
            "-p",
            "--port",
            type=int,
            help=("server port"),
        )
    )

    def inner(f):
        return functools.reduce(lambda x, opt: opt(x), options, f)

    return inner
