import click
from lib.rdtp.operations import run_operation, UploadOperation
from lib.utils import common_options, init_logger


@click.command(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Upload a file to an rdtp server.",
    no_args_is_help=True,
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
    init_logger("upload.log", verbose, quiet)
    run_operation(UploadOperation.opcode, src, host, port, name)


if __name__ == "__main__":
    main()
