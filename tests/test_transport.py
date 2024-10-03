import threading
import logging
from src.lib.rdtp.transport import (
    RDTSegment,
    StopAndWaitTransport,
    SACKTransport,
    WindowSlot,
    sockaddr,
    sack_block,
)
from src.lib.rdtp.server import Server


def basic_server(server):
    logging.info("Starting server")
    try:
        server.start()
    except OSError:
        # server closed
        pass


def test_segment_unpack():
    segment = RDTSegment(b"asd", op_metadata=True)
    unpacked = RDTSegment.unpack(segment.to_bytes())
    assert segment.seq == unpacked.seq
    assert segment.ack == unpacked.ack
    assert segment.op_metadata == unpacked.op_metadata
    assert segment.data == unpacked.data


def test_segment_unpack_with_options():
    segment = RDTSegment(
        b"asd",
        seq=10,
        op_metadata=True,
        sack_options=[sack_block(left_edge=2, right_edge=8)],
    )
    unpacked = RDTSegment.unpack(segment.to_bytes())
    assert segment.seq == unpacked.seq
    assert segment.ack == unpacked.ack
    assert segment.op_metadata == unpacked.op_metadata
    assert segment.sack_options == unpacked.sack_options
    assert segment.data == unpacked.data


def test_update_sack_options():
    transport = SACKTransport()
    transport.sack_options = [
        sack_block(left_edge=20, right_edge=25),
        sack_block(left_edge=10, right_edge=15),
    ]
    transport.ack = 0
    transport._update_sack_options(RDTSegment("aaaaa", 25))
    assert len(transport.sack_options) == 2
    assert transport.sack_options[0].left_edge == 20
    assert transport.sack_options[0].right_edge == 30
    transport._update_sack_options(RDTSegment("bbbbb", 15))
    assert len(transport.sack_options) == 1
    assert transport.sack_options[0].left_edge == 10
    assert transport.sack_options[0].right_edge == 30
    transport._update_sack_options(RDTSegment("ccccc", 0))
    assert len(transport.sack_options) == 1
    assert transport.ack == 5
    assert transport.sack_options[0].left_edge == 10
    assert transport.sack_options[0].right_edge == 30
    transport._update_sack_options(RDTSegment("ddddd", 5))
    assert transport.ack == 30


def test_update_sack_options_2():
    transport = SACKTransport()
    transport.sack_options = [
        sack_block(left_edge=20508, right_edge=32796),
        sack_block(left_edge=28, right_edge=12316),
    ]
    transport._update_sack_options(RDTSegment("a" * 4096, 16412))
    assert len(transport.sack_options) == 2
    assert transport.sack_options[0].left_edge == 16412
    assert transport.sack_options[0].right_edge == 32796


def test_update_sack_options_2():
    transport = SACKTransport()
    transport.ack = 28
    transport.sack_options = [
        sack_block(left_edge=57372, right_edge=65564),
        sack_block(left_edge=16412, right_edge=45084),
        sack_block(left_edge=4124, right_edge=12316),
    ]
    transport._update_sack_options(RDTSegment("a" * 4096, 28))
    assert transport.ack == 12316
    assert len(transport.sack_options) == 2


def test_update_sack_options_3():
    transport = SACKTransport()
    transport.ack = 94236
    transport.sack_options = [
        sack_block(left_edge=127004, right_edge=131100),
        sack_block(left_edge=139292, right_edge=143388),
        sack_block(left_edge=98332, right_edge=135196),
    ]
    transport._update_sack_options(RDTSegment("a" * 4096, 135196))
    assert transport.ack == 94236
    assert len(transport.sack_options) == 2
    assert transport.sack_options[2].left_edge == 98332
    assert transport.sack_options[2].right_edge == 98332 + 4096


def test_update_sack_options_3():
    transport = SACKTransport()
    transport.ack = 94236
    transport.sack_options = [
        sack_block(left_edge=139292, right_edge=143388),
        sack_block(left_edge=98332, right_edge=135196),
    ]
    transport._update_sack_options(RDTSegment("a" * 4096, 127004))
    assert transport.ack == 94236
    assert len(transport.sack_options) == 2
    assert transport.sack_options[0] == sack_block(
        left_edge=139292, right_edge=143388
    )
    assert transport.sack_options[1] == sack_block(
        left_edge=98332, right_edge=135196
    )


def test_update_sack_options_4():
    transport = SACKTransport()
    transport.ack = 94236
    transport.sack_options = [
        sack_block(left_edge=352284, right_edge=356380),
        sack_block(left_edge=372764, right_edge=376860),
        sack_block(left_edge=360476, right_edge=368668),
        sack_block(left_edge=323612, right_edge=348188),
        sack_block(left_edge=217116, right_edge=319516),
    ]
    transport._update_sack_options(RDTSegment("a" * 4096, 368668))
    assert transport.ack == 94236
    assert len(transport.sack_options) == 4
    assert transport.sack_options[0] == sack_block(
        left_edge=352284, right_edge=356380
    )
    assert transport.sack_options[1] == sack_block(
        left_edge=360476, right_edge=376860
    )
    assert transport.sack_options[2] == sack_block(
        left_edge=323612, right_edge=348188
    )
    assert transport.sack_options[3] == sack_block(
        left_edge=217116, right_edge=319516
    )


def test_update_sack_options_5():
    transport = SACKTransport()
    transport.ack = 536611
    transport.sack_options = [
        # sack_block(left_edge=528419, right_edge=536611),
        sack_block(left_edge=610339, right_edge=626723),
        sack_block(left_edge=593955, right_edge=606243),
        sack_block(left_edge=581667, right_edge=589859),
        sack_block(left_edge=548899, right_edge=577571),
        sack_block(left_edge=540707, right_edge=544803),
        sack_block(left_edge=528419, right_edge=536611),
    ]
    transport._update_sack_options(RDTSegment("a" * 4096, 536611))
    assert transport.ack == 544803
    assert len(transport.sack_options) == 5


def test_sack_refill_window_with_sequential_losses_at_the_beginning():
    transport = SACKTransport()
    addr = sockaddr("localhost", 12345)
    transport.window = [
        WindowSlot(RDTSegment(b"asd", 0), addr),  # lost
        WindowSlot(RDTSegment(b"fgh", 3), addr),  # lost
        WindowSlot(RDTSegment(b"jklz", 6), addr),
    ]
    ack = RDTSegment(ack=0, sack_options=[sack_block(6, 10)])
    transport.refill_window(ack)
    assert transport.window_size == 2
    assert transport.window[0].pkt.seq == 0
    assert transport.window[1].pkt.seq == 3


def test_sack_refill_window_with_one_loss():
    transport = SACKTransport()
    addr = sockaddr("localhost", 12345)
    transport.window = [
        WindowSlot(RDTSegment(b"asd", 0), addr),
        WindowSlot(RDTSegment(b"fgh", 3), addr),  # lost
        WindowSlot(RDTSegment(b"jklz", 6), addr),
    ]
    ack = RDTSegment(ack=3, sack_options=[sack_block(6, 10)])
    transport.refill_window(ack)
    assert transport.window_size == 1
    assert transport.window[0].pkt.seq == 3


def test_sack_refill_window_with_sequential_losses_at_the_end():
    transport = SACKTransport()
    addr = sockaddr("localhost", 12345)
    transport.window = [
        WindowSlot(RDTSegment(b"asd", 0), addr),
        WindowSlot(RDTSegment(b"fgh", 3), addr),  # lost
        WindowSlot(RDTSegment(b"jklz", 6), addr),  # lost
    ]
    ack = RDTSegment(ack=3)
    transport.refill_window(ack)
    assert transport.window_size == 2
    assert transport.window[0].pkt.seq == 3
    assert transport.window[1].pkt.seq == 6


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
        assert server.transport.ack == 1
        assert bytes_sent == RDTSegment.DATA_OFFSET + 1
    finally:
        server.close()
        if t.is_alive():
            t.join()


def test_base_sack_send():
    addr = ("localhost", 12345)
    client = SACKTransport()
    server = Server(addr[0], addr[1])
    print(client.read_timeout)
    t = threading.Thread(target=basic_server, args=[server])
    try:
        t.start()
        # send 1 byte of data and wait for ack
        bytes_sent = client.send(b"a", sockaddr(*addr))
        assert client.seq == 1
        assert server.transport.ack == 1
        assert bytes_sent == RDTSegment.DATA_OFFSET + 1
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
        assert server.transport.ack == 10
        assert bytes_sent == 10 + RDTSegment.DATA_OFFSET  # 10 + header (2)
    finally:
        server.close()
        if t.is_alive():
            t.join()
