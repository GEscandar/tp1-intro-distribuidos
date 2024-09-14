import threading
import logging
from rdtp import RDTTransport, StopAndWaitTransport, sockaddr


def basic_server(host, port):
    server = RDTTransport()
    server.sock.bind((host, port))
    logging.info("Starting server")
    while True:
        try:
            server.receive(1024)
        except TimeoutError:
            continue
        finally:
            server.close()
            break


def test_base_send():
    client = StopAndWaitTransport()
    addr = ("localhost", 12345)
    t = threading.Thread(target=basic_server, args=addr)
    try:
        t.start()
        client.send(b"a", sockaddr(*addr))
    finally:
        t.join()
