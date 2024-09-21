import threading
import logging
from rdtp import RDTTransport, RDTSegment, Server, StopAndWaitTransport, sockaddr


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
    server = Server(addr[1])
    print(client.read_timeout)
    t = threading.Thread(target=basic_server, args=[server])
    try:
        t.start()
        # send 1 byte of data and wait for ack
        client.send(b"a", sockaddr(*addr))
        assert client.seq == 1
        assert client.ack == 1
    finally:
        server.close()
        if t.is_alive():
            t.join()
