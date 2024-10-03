import logging
import threading
import time
import os
from pathlib import Path
from src.lib.rdtp.transport import get_transport_factory
from src.lib.rdtp.server import FileTransferServer
from src.lib.rdtp.operations import (
    DownloadOperation,
    run_operation,
    unpack_operation,
)


def basic_server(server):
    logging.info("Starting server")
    try:
        server.start()
    except (OSError, ValueError):
        # server closed
        pass


def download(addr, filepath: Path, is_sack=False):
    storage_path = Path("server_storage")
    transport_factory = get_transport_factory(is_sack)
    server = FileTransferServer(
        addr[0], addr[1], storage_path, transport_factory=transport_factory
    )
    client = transport_factory()
    # print(client.read_timeout)
    created_file = Path(filepath.name)
    t = threading.Thread(target=basic_server, args=[server])
    try:
        t.start()
        # run the download operation
        run_operation(
            DownloadOperation.opcode,
            str(filepath.absolute()),
            addr[0],
            addr[1],
            filepath.name,
        )
        time.sleep(0.1)  # wait till the client saves the file
        assert created_file.exists()
        assert created_file.stat().st_size == filepath.stat().st_size
    finally:
        client.close()
        server.close()
        if t.is_alive():
            t.join()
        if created_file.exists():
            created_file.unlink()


def test_download_operation_unpack():
    filepath = Path("tests", "files", "small.txt")
    op = DownloadOperation(None, filepath.name, filepath.name)
    unpacked = unpack_operation(None, op.get_op_metadata())
    assert op.filename == unpacked.filename
    # assert op.destination == unpacked.destination


def test_download_small_file():
    addr = ("localhost", 34567)
    filepath = Path("tests", "files", "small.txt")
    download(addr, filepath)


def test_download_medium_small_file():
    addr = ("localhost", 34568)
    filepath = Path("tests", "files", "medium_small.txt")
    download(addr, filepath)


def test_download_medium_file():
    addr = ("localhost", 34569)
    filepath = Path("tests", "files", "medium.txt")
    download(addr, filepath)


def test_sack_download_small_file():
    addr = ("localhost", 34570)
    filepath = Path("tests", "files", "small.txt")
    download(addr, filepath, is_sack=True)


def test_sack_download_medium_small_file():
    addr = ("localhost", 34571)
    filepath = Path("tests", "files", "medium_small.txt")
    download(addr, filepath, is_sack=True)


def test_sack_download_medium_file():
    addr = ("localhost", 34572)
    filepath = Path("tests", "files", "medium.txt")
    download(addr, filepath, is_sack=True)
