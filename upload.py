import click
from rdtp.operations import run_operation, UploadOperation
from utils import common_options


@click.command(
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
@common_options()
@click.pass_context
def main(
    ctx: click.Context,
    src: str,
    name: str,
    verbose: bool,
    quiet: bool,
    host: str,
    port: int,
):
    print(f"valores: {src} ,{name},{verbose} , {host}, {port}")
    run_operation(UploadOperation.opcode, src, host, port, name)


if __name__ == "__main__":
    main()
