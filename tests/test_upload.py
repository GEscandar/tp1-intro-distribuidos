import logging
import threading
import time
from pathlib import Path
from src.lib.rdtp.transport import StopAndWaitTransport
from src.lib.rdtp.server import FileTransferServer
from src.lib.rdtp.operations import UploadOperation, run_operation


def basic_server(server):
    logging.info("Starting server")
    try:
        server.start()
    except (OSError, ValueError):
        # server closed
        pass


def upload(addr, filepath: Path):
    storage_path = Path("server_storage")
    server = FileTransferServer(addr[0], addr[1], storage_path)
    client = StopAndWaitTransport()
    # print(client.read_timeout)
    created_file = Path(storage_path, filepath.name)
    t = threading.Thread(target=basic_server, args=[server])
    try:
        t.start()
        # run the upload operation
        run_operation(
            UploadOperation.opcode, filepath.absolute(), addr[0], addr[1], filepath.name
        )
        time.sleep(0.1)  # wait till the server saves the file
        assert created_file.exists()
        assert created_file.stat().st_size == filepath.stat().st_size
    finally:
        client.close()
        server.close()
        if t.is_alive():
            t.join()
        if created_file.exists():
            created_file.unlink()


def test_upload_small_file():
    addr = ("localhost", 23456)
    filepath = Path("tests", "files", "small.txt")
    upload(addr, filepath)


def test_upload_medium_small_file():
    addr = ("localhost", 23457)
    filepath = Path("tests", "files", "medium_small.txt")
    upload(addr, filepath)


def test_upload_medium_file():
    addr = ("localhost", 23458)
    filepath = Path("tests", "files", "medium.txt")
    upload(addr, filepath)
