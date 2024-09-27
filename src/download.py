import click
from lib.rdtp.operations import run_operation, DownloadOperation
from lib.utils import common_options, init_logger


@click.command(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Upload a file to an rdtp server.",
    no_args_is_help=True,
)
@click.option(
    "-d",
    "--dst",
    type=click.Path(
        exists=False, file_okay=True, dir_okay=True, readable=True, path_type=str
    ),
    help="destination file path",
)
@click.option(
    "-n",
    "--name",
    help="file name",
)
@common_options()
@click.pass_context
def main(
    ctx: click.Context,
    dst: str,
    name: str,
    verbose: bool,
    quiet: bool,
    host: str,
    port: int,
):
    init_logger("download.log", verbose, quiet)
    run_operation(DownloadOperation.opcode, name, host, port, dst)


if __name__ == "__main__":
    main()
