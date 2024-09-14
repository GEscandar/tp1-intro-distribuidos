import click
import functools
from typing import Optional
from .transport import *
from .server import Server
from .exceptions import *


def common_options(f):
    options = [
        click.option(
            "-l",
            "--location",
            help="IPv4 Address of the rdtp server.",
        ),
        click.option(
            "-v",
            "--verbose",
            is_flag=True,
            help=("Emit messages about ongoing file transfer operations"),
        ),
        click.option(
            "-w",
            "--workers",
            type=click.IntRange(min=1),
            default=None,
            help=(
                "When rdtp uploads or downloads a large file, it may use a process pool to"
                " speed up processing. This option controls the number of parallel workers."
                " This can also be specified via the RDTP_NUM_WORKERS environment variable."
                " Defaults to the number of CPUs in the system."
            ),
        ),
    ]
    return functools.reduce(lambda x, opt: opt(x), options, f)


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="A safe UDP file transfer tool.",
)
@click.pass_context
def main(
    ctx: click.Context,
):
    pass


@main.command(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Upload a file to an rdtp server.",
)
@click.option(
    "-f",
    "--file",
    type=click.Path(
        exists=True, file_okay=True, dir_okay=True, readable=True, path_type=str
    ),
    help="Path of the file to send.",
)
@common_options
@click.pass_context
def upload(
    ctx: click.Context,
    file: str,
    location: str,
    verbose: bool,
    workers: Optional[int],
):
    print(location)
    print(verbose)
    print(file)
    # rdtp_upload(file, location, workers=workers)


if __name__ == "__main__":
    main()
