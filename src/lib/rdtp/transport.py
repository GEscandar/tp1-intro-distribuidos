import socket
import logging
import select
import sys
import random
from dataclasses import dataclass, astuple
from typing import Union, Tuple, List
from .exceptions import ConnectionError

MAX_RETRIES = 100
MAX_READ_TIMEOUT = 1.0
MIN_READ_TIMEOUT = 0.01
DEFAULT_TIMEOUT = 2
SACK_WINDOW_SIZE = 20
RECV_CHUNK_SIZE = 4096

__all__ = [
    "sockaddr",
    "RDTSegment",
    "RDTTransport",
    "StopAndWaitTransport",
    "SACKTransport",
    "get_transport_factory",
]


def get_transport_factory(is_sack: bool):
    if is_sack:
        return SACKTransport
    return StopAndWaitTransport


@dataclass
class sockaddr:
    """Representation of an IPv4 socket address"""

    host: str
    port: int

    def as_tuple(self):
        return astuple(self)


@dataclass
class sack_block:
    """Representation of a selective acknowledgement (SACK) block"""

    left_edge: int
    right_edge: int


class RDTSegment:
    """An RDTP (Reliable Data Transfer Protocol) segment"""

    """Size of the sequence number in bytes"""
    SEQ_SIZE = 4
    ACK_SIZE = SEQ_SIZE
    DATA_OFFSET_SIZE = 2
    DATA_OFFSET = SEQ_SIZE + ACK_SIZE + DATA_OFFSET_SIZE + 1

    """Max Size of the segment header in bytes"""
    HEADER_SIZE = DATA_OFFSET + 4 + 8 * 255

    def __init__(
        self,
        data: bytes = bytes(),
        seq: int = 0,
        ack: int = 0,
        op_metadata=False,
        sack_options: List[sack_block] = None,
    ):
        self.data = data
        self.seq = seq
        self.ack = ack
        self.op_metadata = op_metadata
        self.data_offset = RDTSegment.DATA_OFFSET
        self.sack_options = sack_options or []
        if self.sack_options:
            self.data_offset += 4 + 8 * len(self.sack_options)

    @property
    def expected_ack(self):
        return self.seq + len(self.data)

    @staticmethod
    def unpack(data: bytes):
        seq = int.from_bytes(data[: RDTSegment.SEQ_SIZE], byteorder=sys.byteorder)
        data = data[RDTSegment.SEQ_SIZE :]

        ack = int.from_bytes(data[: RDTSegment.SEQ_SIZE], byteorder=sys.byteorder)
        data = data[RDTSegment.SEQ_SIZE :]
        op_metadata = bool.from_bytes(data[:1], byteorder=sys.byteorder)
        data_offset = int.from_bytes(
            data[1 : 1 + RDTSegment.DATA_OFFSET_SIZE], byteorder=sys.byteorder
        )
        data = data[1 + RDTSegment.DATA_OFFSET_SIZE :]

        sack_options = None
        if data_offset > RDTSegment.DATA_OFFSET:
            sack_options = []
            length = int.from_bytes(data[:4], byteorder=sys.byteorder)
            data = data[4:]
            for i in range(length):
                offset = i * 8
                sack_options.append(
                    sack_block(
                        left_edge=int.from_bytes(
                            data[offset : offset + 4], byteorder=sys.byteorder
                        ),
                        right_edge=int.from_bytes(
                            data[offset + 4 : offset + 8], byteorder=sys.byteorder
                        ),
                    )
                )
            data = data[length * 8 :]

        return RDTSegment(
            data, seq, ack, op_metadata=op_metadata, sack_options=sack_options
        )

    def to_bytes(self):
        res = self.seq.to_bytes(RDTSegment.SEQ_SIZE, byteorder=sys.byteorder)
        res += self.ack.to_bytes(RDTSegment.SEQ_SIZE, byteorder=sys.byteorder)
        res += self.op_metadata.to_bytes(1, byteorder=sys.byteorder)
        res += self.data_offset.to_bytes(
            RDTSegment.DATA_OFFSET_SIZE, byteorder=sys.byteorder
        )
        if self.sack_options:
            res += len(self.sack_options).to_bytes(4, sys.byteorder)
            for block in self.sack_options:
                res += block.left_edge.to_bytes(4, sys.byteorder)
                res += block.right_edge.to_bytes(4, sys.byteorder)
        res += self.data
        return res

    def __bytes__(self):
        return self.to_bytes()

    def __str__(self):
        return (
            "seq: {}, ack: {}, len(data): {}, op_metadata: {}, sack_options: {}".format(
                self.seq, self.ack, len(self.data), self.op_metadata, self.sack_options
            )
        )


class RDTTransport:
    """Base class for RDTP transport implementations"""

    def __init__(
        self,
        sock: socket.socket = None,
        sock_timeout: float = None,
        read_timeout: float = MIN_READ_TIMEOUT,
    ) -> None:
        if not sock:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if sock_timeout is not None:
            sock.settimeout(sock_timeout)
        if read_timeout is None:
            raise ValueError("read_timeout cannot be None")
        self.sock = sock
        self.read_timeout = read_timeout
        self.closed = False
        self.seq = 0
        self.ack = 0

    def __enter__(self, *args):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def _sockfd(self):
        return self.sock.fileno()

    def _create_segment(
        self,
        data: bytes = None,
        seq: int = None,
        ack: int = None,
        op_metadata=False,
        sack_options=None,
    ):
        data = data or bytes()
        seq = seq or self.seq
        ack = ack or self.ack
        return RDTSegment(
            data=data,
            seq=seq,
            ack=ack,
            op_metadata=op_metadata,
            sack_options=sack_options,
        )

    def _send(self, segment: RDTSegment, address: sockaddr) -> int:
        """Try to send the RDT segment to the server at ```address```.
        This is only meant to be called by implementations of this class.

        Args:
            data (Any): Data to send
            address (sockaddr): Server address

        Returns:
            int: The number of bytes sent to the server
        """
        data_len = len(segment.data)
        try:
            data = bytes(segment)
        except TypeError as e:
            raise ValueError(f"Error converting data to bytes: {e}")

        sent = False
        while not sent:
            try:
                bytes_sent = self.sock.sendto(data, address.as_tuple())
                sent = True
            except BlockingIOError:
                import time

                time.sleep(0.001)
        # bytes_sent = self.send_all(data, len(data), address.as_tuple())
        logging.debug(
            f"Sent {bytes_sent} bytes to {address}, with data_len={data_len}, seq={segment.seq}, ack={segment.ack}"
        )
        if self.seq == segment.seq:
            # After sending, increment the seq number if this is not a retransmission
            self.seq += data_len
        return bytes_sent

    def send(
        self, data: bytes, address: sockaddr, op_metadata=False, max_retries=MAX_RETRIES
    ) -> int:
        raise NotImplementedError

    def handshake(self, address: sockaddr):
        logging.debug(f"Sending handshake message to: {address}")
        for i in range(MAX_RETRIES + 1):
            try:
                self._send(self._create_segment(), address)
                _, new_addr = self.read(0)
                break
            except (TimeoutError, BlockingIOError):
                if i == MAX_RETRIES:
                    raise ConnectionError("Unable to connect")
        logging.debug(f"Finished handshake, now talking to: {new_addr}")
        return new_addr

    def _ack(self, pkt: RDTSegment, addr: sockaddr):
        """Send an acknowledgement for the received packet

        Args:
            pkt (RDTSegment): The received packet
            addr (sockaddr): Peer address
        """
        pkt_len = len(pkt.data)
        logging.debug(
            f"Received packet of length: {pkt_len} seq: {pkt.seq}, expected seq={self.ack}"
        )
        if pkt.seq == self.ack:
            if pkt.data:
                # got a non-empty data packet, increase ack number by the packet's length
                self.ack += pkt_len
        elif pkt.seq < self.ack:
            # retransmission, drop packet
            logging.debug("Retransmission, dropping packet")
            pkt.data = bytes()

        ack_pkt = self._create_segment()
        logging.debug(
            f"got package with seq={pkt.seq}, length={pkt_len}. sending ACK to {addr}. pkt=[{ack_pkt}]"
        )
        if pkt_len or self.ack == 0:
            self._send(ack_pkt, addr)

    def read(self, bufsize: int):
        if not self.closed:
            if self.read_timeout > 0:
                ready = select.select(
                    [self._sockfd],
                    [],
                    [],
                    self.read_timeout,
                )
                if ready[0]:
                    logging.debug(f"Reading fd {self._sockfd}: {ready}")
                    data, addr = self.sock.recvfrom(bufsize + RDTSegment.HEADER_SIZE)
                    # logging.debug(data)
                else:
                    raise TimeoutError("Socket read timed out")
            else:
                # this raises BlockingIOError if data is not yet available to read
                data, addr = self.sock.recvfrom(bufsize + RDTSegment.HEADER_SIZE)
            return RDTSegment.unpack(data), sockaddr(*addr)
        raise ConnectionError("Socket closed")

    def receive(self, bufsize=RECV_CHUNK_SIZE, ack=True, max_retries=MAX_RETRIES):
        """
        Receive data through the socket, stripping the headers.
        Emits the corresponding ACK to the sending end.
        """
        for i in range(max_retries + 1):
            try:
                pkt, addr = self.read(bufsize)
                if i <= 3 and self.read_timeout > MIN_READ_TIMEOUT:
                    logging.debug(f"Took {i} attempts to read, halving read timeout")
                    self.read_timeout /= 2
                break
            except (TimeoutError, BlockingIOError):
                if i == max_retries:
                    raise
                elif i > 0 and i % 3 == 0 and self.read_timeout < MAX_READ_TIMEOUT:
                    logging.debug(f"Took {i} attempts to read, doubling read timeout")
                    self.read_timeout *= 2
                continue
        if ack:
            self._ack(pkt, addr)
        return pkt, addr

    def close(self):
        if not self.closed:
            logging.debug("Closing UDP socket")
            try:
                self.sock.close()
            # except Exception as e:
            #     logging.error(e)
            finally:
                self.closed = True


class StopAndWaitTransport(RDTTransport):

    def send(
        self, data: bytes, address: sockaddr, op_metadata=False, max_retries=MAX_RETRIES
    ) -> int:
        segment = self._create_segment(data, op_metadata=op_metadata)
        for nattempt in range(max_retries + 1):
            try:
                bytes_sent = self._send(
                    segment,
                    address,
                )
                logging.debug(f"Waiting for ack... (nattempt={nattempt})")
                ack_segment, _ = self.read(0)
                logging.debug(
                    f"Received ack: {ack_segment.ack}, expected ack={self.seq}, nattempt={nattempt}"
                )
                if ack_segment.ack != self.seq:
                    if (
                        nattempt > 0
                        and nattempt % 3 == 0
                        and self.read_timeout < MAX_READ_TIMEOUT
                    ):
                        # triple retransmission, double read_timeout
                        self.read_timeout *= 2
                    continue
                elif nattempt < 4 and self.read_timeout > MIN_READ_TIMEOUT:
                    self.read_timeout /= 2
                return bytes_sent
            except (TimeoutError, BlockingIOError):
                if (
                    nattempt > 0
                    and nattempt % 3 == 0
                    and self.read_timeout < MAX_READ_TIMEOUT
                ):
                    # triple retransmission, double read_timeout
                    self.read_timeout += MIN_READ_TIMEOUT
                continue
        raise ConnectionError("Connection lost")


@dataclass
class WindowSlot:
    pkt: RDTSegment
    addr: sockaddr

    def __repr__(self) -> str:
        return f"WindowSlot(segment=[{self.pkt}], addr={self.addr})"


class SACKTransport(RDTTransport):
    def __init__(
        self,
        sock: socket.socket = None,
        sock_timeout: float = 0,
        read_timeout: float = MIN_READ_TIMEOUT,
    ) -> None:
        super().__init__(sock, sock_timeout, read_timeout)
        self.window: List[WindowSlot] = []
        self.recvbuf: List[WindowSlot] = []
        self.iterbuf = self._iterbuf()
        self.sack_options: List[sack_block] = []
        self.nttempts = 0
        self._buf_yielded = False

    @property
    def window_size(self):
        return len(self.window)

    def _create_segment(
        self,
        data: bytes = None,
        seq: int = None,
        ack: int = None,
        op_metadata=False,
        sack_options=None,
    ):
        sack_options = sack_options or self.sack_options
        return super()._create_segment(
            data, seq, ack, op_metadata, sack_options=sack_options
        )

    def _save_packet(self, pkt: RDTSegment, addr: sockaddr):
        """Insert the packet in the recvbuf in order,
        sorting by seq number.

        Args:
            pkt (RDTSegment): The received packet
            addr (sockaddr): Sender address
        """
        import copy

        logging.debug(f"Saving packet [{pkt}] in recvbuf")
        slot = WindowSlot(
            # self._create_segment(
            #     pkt.data,
            #     seq=pkt.seq,
            #     ack=pkt.ack,
            #     op_metadata=pkt.op_metadata,
            #     sack_options=None,
            # ),
            copy.deepcopy(pkt),
            addr,
        )
        for i, _slot in enumerate(self.recvbuf):
            if slot.pkt.seq < _slot.pkt.seq:
                self.recvbuf.insert(i, slot)
                break
            elif slot.pkt.seq == _slot.pkt.seq:
                break
        else:
            self.recvbuf.append(slot)

    def _iterbuf(self):
        while True:
            if self.recvbuf:
                logging.debug(f"{self.recvbuf[0]} => {self.ack}")
            if self.recvbuf and self.recvbuf[0].pkt.expected_ack <= self.ack:
                self._buf_yielded = True
                p = self.recvbuf.pop(0)
                logging.debug(f"Popping packet: {p}")
                yield p
            else:
                yield None

    def pop_recv(self):
        return next(self.iterbuf)

    def _update_sack_options(self, pkt: RDTSegment):
        # 0-500 -> ACK 500
        # 500-1000 -> loss
        # 1000-1500 -> ACK 500 [(1000,1500),(0,500)]
        # 1500-2000 -> loss
        # 2000-2500 -> ACK 500 [(2000,2500),(1000,1500),(0,500)]
        # 500-1000 -> ACK 1500 [(2000,2500),(0,1500)]
        # 2500-3000 -> ACK 1500 [(2000,3000),(0,1500)]
        # 1500-2000 -> ACK 3000
        logging.debug(
            f"Updating sack options with packet: (seq={pkt.seq}, expected_ack={pkt.expected_ack})"
        )
        pkt_opt = sack_block(left_edge=pkt.seq, right_edge=pkt.expected_ack)
        _opts = []
        i = 0
        j = 1
        coalesced = False
        while i < len(self.sack_options):
            opt = self.sack_options[i]
            if (
                pkt_opt.left_edge >= opt.left_edge
                and pkt_opt.right_edge <= opt.right_edge
            ):
                # pkt_opt contained within opt
                coalesced = True
            elif opt.left_edge == pkt_opt.right_edge:
                # coalesce to the left
                opt.left_edge = pkt_opt.left_edge
                coalesced = True
            elif opt.right_edge == pkt_opt.left_edge:
                # coalesce to the right
                opt.right_edge = pkt_opt.right_edge
                coalesced = True
            if coalesced:
                if pkt.seq == self.ack:
                    self.ack = opt.right_edge
                if j < len(self.sack_options):
                    pkt_opt = self.sack_options[j]
                    j += 1
                    continue
            if i == 0 or (
                i > 0
                and not (
                    opt.left_edge >= _opts[-1].left_edge
                    and opt.right_edge <= _opts[-1].right_edge
                )
                and opt.right_edge != self.ack
            ):
                _opts.append(opt)
            i += 1
        if not coalesced:
            if pkt.seq != self.ack:
                if _opts and pkt_opt.left_edge > _opts[0].right_edge:
                    _opts.insert(0, pkt_opt)
                else:
                    _opts.append(pkt_opt)
            else:
                self.ack += len(pkt.data)
        self.sack_options = _opts

        if len(self.sack_options) == 1 and self.sack_options[0].right_edge == self.ack:
            # all packets acknowledged, reinitialize sack_options
            logging.debug("All packets acknowledged, reinitializing sack_options")
            self.sack_options = []

        logging.debug(
            f"SACK options new value => {"\n".join(str(opt) for opt in self.sack_options)}"
        )

    def _ack(self, pkt: RDTSegment, addr: sockaddr):
        if self._buf_yielded:
            self._buf_yielded = False
            return
        logging.debug(
            f"Received packet of length: {len(pkt.data)} seq: {pkt.seq}, expected seq={self.ack}"
        )
        out_of_order = False
        if pkt.seq > self.ack and pkt.data:
            out_of_order = True
            logging.debug("Packet out of order")
            self._save_packet(pkt, addr)
        elif pkt.seq < self.ack:
            return super()._ack(pkt, addr)

        self._update_sack_options(pkt)

        # send ack
        sent = 0
        if pkt.data or self.ack == 0:
            logging.debug("Sending ack")
            sent = self._send(self._create_segment(), addr)

        if out_of_order:
            pkt.data = bytes()

        return sent

    def _ensure_empty_window(self, max_retries=MAX_RETRIES):
        nattempt = 0
        while self.window and nattempt < max_retries:
            self.resend_window()
            nattempt += 1
        if nattempt == max_retries:
            raise ConnectionError("Connection lost")

    def read(self, bufsize):
        slot = self.pop_recv()
        if slot:
            return slot.pkt, slot.addr
        return super().read(bufsize)

    def receive(self, bufsize=RECV_CHUNK_SIZE, ack=True, max_retries=MAX_RETRIES):
        self._ensure_empty_window()
        pkt, addr = super().receive(bufsize, ack, max_retries)
        while pkt.seq > self.ack:
            pkt, addr = super().receive(bufsize, ack, max_retries)
        return pkt, addr

    def refill_window(self, ack_segment: RDTSegment):
        if not self.window:
            return
        elif ack_segment.ack == 0 and not ack_segment.sack_options:
            logging.debug("Nothing to refill")
            return
        logging.debug(
            f"Refilling window: {"\n".join(str(slot) for slot in self.window)},\n ack=[{ack_segment}]"
        )
        _window = []
        for slot in self.window:
            acked = False
            if ack_segment.sack_options:
                for opt in ack_segment.sack_options:
                    if (
                        slot.pkt.seq >= opt.left_edge
                        and slot.pkt.expected_ack <= opt.right_edge
                    ):
                        # mark slot as acknowledged
                        acked = True
                        break
            if not acked and slot.pkt.expected_ack > ack_segment.ack:
                _window.append(slot)
        self.window = _window
        logging.debug(f"New window: {"\n".join(str(slot) for slot in self.window)}")

    def resend_window(self, max_retries=MAX_RETRIES):
        logging.debug(f"Resending window")
        self.nttempts += 1
        for slot in self.window:
            self._send(slot.pkt, slot.addr)
            try:
                ack_segment, _ = self.read(0)
                self.refill_window(ack_segment)
            except TimeoutError:
                if self.nttempts == max_retries:
                    raise ConnectionError("Connection lost")

    def send(
        self, data: bytes, address: sockaddr, op_metadata=False, max_retries=MAX_RETRIES
    ) -> int:
        bytes_sent = 0
        segment = self._create_segment(data, op_metadata=op_metadata)

        # if the window is not full, send the packet
        if self.window_size < SACK_WINDOW_SIZE:

            bytes_sent = self._send(segment, address)
            self.window.append(WindowSlot(segment, address))
        else:
            # otherwise, block until we manage to free a slot in the window
            # and only then send the packet
            logging.debug("Window full, waiting for ack")
            try:
                ack_segment, _ = self.read(0)
                self.refill_window(ack_segment)
            except TimeoutError:
                # if no ACK arrives, resend all packets in the window, till
                # we get an ACK. If that doesn't work, raise ConnectionError
                self.resend_window(max_retries)
            logging.debug("Retrying send")
            return self.send(data, address)

        # the packet was sent, so wait for an ack without blocking
        try:
            ack_segment, _ = self.read(0)
            logging.debug(f"Received ack: {ack_segment.ack}, expected ack={self.seq}")
            if ack_segment.ack == self.window[-1].pkt.expected_ack:
                self.window.pop()
            else:
                self.refill_window(ack_segment)
        except TimeoutError:
            pass

        return bytes_sent

    def close(self):
        try:
            self._ensure_empty_window()
        finally:
            super().close()
