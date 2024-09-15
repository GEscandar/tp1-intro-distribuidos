import logging
import threading
import os
from pathlib import Path
from rdtp.transport import StopAndWaitTransport, sockaddr
from rdtp.server import FileTransferServer
from rdtp.operations import UploadOperation, run_operation


def basic_server(host, port):
    server = FileTransferServer(port)
    logging.info("Starting server")
    server.start(wait=False)


def test_upload_small_file():
    client = StopAndWaitTransport()
    print(client.read_timeout)
    addr = ("localhost", 23456)
    filepath = Path("tests", "files", "small.txt")
    t = threading.Thread(target=basic_server, args=addr)
    try:
        t.start()
        # run the upload operation
        run_operation(
            UploadOperation.opcode, filepath.absolute(), addr[0], addr[1], filepath.name
        )
        created_file = Path(filepath.name)
        assert created_file.exists()
        assert created_file.stat().st_size == filepath.stat().st_size
        created_file.unlink()
    finally:
        if t.is_alive():
            t.join()
        client.close()
