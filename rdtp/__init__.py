import click
import functools
from typing import Optional
from .transport import *
from .server import Server
from .exceptions import *
from .operations import run_operation, UploadOperation


def common_options(f):
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
        click.option(
            "-H",
            "--host",
            help=("server IP address"),
        ),
        click.option(
            "-p",
            "--port",
            type=int,
            help=("server port"),
        ),
        # click.option(
        #     "-w",
        #     "--workers",
        #     type=click.IntRange(min=1),
        #     default=None,
        #     help=(
        #         "When rdtp uploads or downloads a large file, it may use a process pool to"
        #         " speed up processing. This option controls the number of parallel workers."
        #         " This can also be specified via the RDTP_NUM_WORKERS environment variable."
        #         " Defaults to the number of CPUs in the system."
        #     ),
        # ),
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
    "-s",
    "--src",
    type=click.Path(
        exists=True, file_okay=True, dir_okay=True, readable=True, path_type=str
    ),
    help="source file path",
)
@click.option(
    "-n",
    "--name",
    help="file name",
)
@common_options
@click.pass_context
def upload(
    ctx: click.Context, src: str, name: str, verbose: bool, host: str, port: int
):
    run_operation(UploadOperation.opcode, src, host, port, name)


if __name__ == "__main__":
    main()
