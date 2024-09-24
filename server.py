from pathlib import Path
import click
from rdtp.server import FileTransferServer
from utils import common_options


@click.command(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Upload a file to an rdtp server.",
)
@click.option(
    "-s",
    "--storage",
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, readable=True, path_type=str
    ),
    help="folder path, used for files upload and download",
)
@common_options(host=False)
@click.pass_context
def main(ctx: click.Context, storage: Path, verbose: bool, quiet: bool, port: int):
    print(f"Starting server at port {port}")
    addr = ("", port)
    server = FileTransferServer(*addr, storage)

    server.start()


if __name__ == "__main__":
    main()
