from pathlib import Path
import click
from lib.rdtp.server import FileTransferServer
from lib.utils import common_options


@click.command(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Upload a file to an rdtp server.",
    no_args_is_help=True,
)
@click.option(
    "-s",
    "--storage",
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, readable=True, path_type=str
    ),
    help="folder path, used for files upload and download",
)
@common_options(host=True)
@click.pass_context
def main(ctx: click.Context, storage: Path, verbose: bool, quiet: bool, host:str, port: int):
    print(f"Starting server at port {port}")
    addr = ("", port)
    server = FileTransferServer(*addr, storage)

    server.start()


if __name__ == "__main__":
    main()