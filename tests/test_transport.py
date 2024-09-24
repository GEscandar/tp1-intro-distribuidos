import threading
import logging
from src.lib.rdtp.transport import RDTSegment, StopAndWaitTransport, sockaddr
from src.lib.rdtp.server import Server


def basic_server(server):
    logging.info("Starting server")
    try:
        server.start()
    except OSError:
        # server closed
        pass


def test_segment_unpack():
    segment = RDTSegment(b"asd")
    unpacked = RDTSegment.unpack(segment.to_bytes())
    assert segment.data == unpacked.data
    assert segment.seq == unpacked.seq
    assert segment.ack == unpacked.ack


def test_base_send():
    addr = ("localhost", 12345)
    client = StopAndWaitTransport()
    server = Server(addr[0], addr[1])
    print(client.read_timeout)
    t = threading.Thread(target=basic_server, args=[server])
    try:
        t.start()
        # send 1 byte of data and wait for ack
        bytes_sent = client.send(b"a", sockaddr(*addr))
        assert client.seq == 1
        assert client.ack == 1
        assert bytes_sent == RDTSegment.HEADER_SIZE + 1
    finally:
        server.close()
        if t.is_alive():
            t.join()


def test_complete_send():
    addr = ("localhost", 12346)
    client = StopAndWaitTransport()
    server = Server(addr[0], addr[1])
    t = threading.Thread(target=basic_server, args=[server])
    try:
        t.start()
        # send 1 byte of data and wait for ack
        bytes_sent = client.send(b"aaaaaaaaaa", sockaddr(*addr))
        print(f"bytes sent: {bytes_sent}")
        assert client.seq == 10
        assert client.ack == 10
        assert bytes_sent == 10 + RDTSegment.HEADER_SIZE  # 10 + header (2)
    finally:
        server.close()
        if t.is_alive():
            t.join()
