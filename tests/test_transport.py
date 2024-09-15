import threading
import logging
from rdtp import RDTTransport, Server, StopAndWaitTransport, sockaddr


def basic_server(host, port):
    server = Server(port)
    logging.info("Starting server")
    server.start(wait=False)


def test_base_send():
    client = StopAndWaitTransport()
    print(client.read_timeout)
    addr = ("localhost", 12345)
    t = threading.Thread(target=basic_server, args=addr)
    try:
        t.start()
        # send 1 byte of data and wait for ack
        bytes_sent = client.send(b"a", sockaddr(*addr))
        assert client.seq == 1
        assert client.ack == 1
        assert bytes_sent == 3
    finally:
        if t.is_alive():
            t.join()

def test_complete_send():
    client = StopAndWaitTransport()
    addr = ("localhost", 12346)
    t = threading.Thread(target=basic_server, args=addr)
    try:
        t.start()
        # send 1 byte of data and wait for ack
        bytes_sent = client.send(b"aaaaaaaaaa", sockaddr(*addr))
        print(f"bytes sent: {bytes_sent}")
        assert client.seq == 10
        assert client.ack == 10
        assert bytes_sent == 12 # 10 + header (2)
    finally:
        if t.is_alive():
            t.join()    