import click
import functools
import logging

class CustomFormatter(logging.Formatter):

    # COLOUR CONSTANTS
    COLOR_GREEN = '\033[92m'
    COLOR_BLUE = '\033[94m'
    COLOR_RED = '\033[91m'
    COLOR_END = '\033[0m'

    FORMATS = {
        logging.DEBUG: f"%(asctime)s - {COLOR_GREEN} [ %(levelname)s ]\
             {COLOR_END} - %(message)s (%(filename)s:%(lineno)d)",
        logging.INFO: f"%(asctime)s - {COLOR_BLUE} [ %(levelname)s ]\
             {COLOR_END} - %(message)s (%(filename)s:%(lineno)d)",
        logging.ERROR: f"%(asctime)s - {COLOR_RED} [ %(levelname)s ]\
             {COLOR_END} - %(message)s (%(filename)s:%(lineno)d)"}

    def format(self, record):
        log_format = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_format)
        return formatter.format(record)


def get_log_level(verbose, quiet):
    if verbose:
        return logging.DEBUG
    elif quiet:
        return logging.ERROR
    else:
        return logging.INFO


def init_logger(filename, verbose=False, quiet=False):
    verbosity = get_log_level(verbose, quiet)
    logging.basicConfig(
        filename=filename,
        level=verbosity,
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S'
    )

    log = logging.getLogger('')
    ch = logging.StreamHandler()
    ch.setLevel(verbosity)
    ch.setFormatter(CustomFormatter())
    log.addHandler(ch)

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
