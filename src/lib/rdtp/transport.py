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
SACK_WINDOW_SIZE = 30

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

    @staticmethod
    def increment(seq):
        return (seq + 1) % (1 << 8 * RDTSegment.SEQ_SIZE)


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

    def send_all(self, data: bytes, amount: int, address: sockaddr):
        bytes_sent = 0
        while bytes_sent < amount:
            bytes_sent += self.sock.sendto(data[bytes_sent:], address)
        return bytes_sent

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

        bytes_sent = self.sock.sendto(data, address.as_tuple())
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
        return self._send(ack_pkt, addr)

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
                else:
                    raise TimeoutError("Socket read timed out")
            else:
                # this raises BlockingIOError if data is not yet available to read
                data, addr = self.sock.recvfrom(bufsize + RDTSegment.HEADER_SIZE)
            return RDTSegment.unpack(data), sockaddr(*addr)
        raise ConnectionError("Socket closed")

    def receive(self, bufsize, ack=True, max_retries=0):
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

    def close(self, wait=False):
        # Wait for resends due to packet loss
        # for _ in range(MAX_RETRIES + 1):
        #     try:
        #         self.receive(1024)
        #     except (TimeoutError, BlockingIOError):
        #         if not wait:
        #             break
        #         continue
        if not self.closed:
            logging.debug("Closing UDP socket")
            try:
                self.sock.close()
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
                logging.debug("Waiting for ack...")
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
                continue
        raise ConnectionError("Connection lost")


@dataclass
class WindowSlot:
    pkt: RDTSegment
    addr: sockaddr
    nresent = 0

    def __repr__(self) -> str:
        return f"WindowSlot(segment=[{self.pkt}], addr={self.addr}, nresent={self.nresent})"


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
        self.nacks = 0
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
        """
        logging.debug(f"Saving packet [{pkt}] in recvbuf")
        slot = WindowSlot(
            self._create_segment(
                pkt.data,
                seq=pkt.seq,
                ack=pkt.ack,
                op_metadata=pkt.op_metadata,
                sack_options=None,
            ),
            addr,
        )
        for i, _slot in enumerate(self.recvbuf):
            if slot.pkt.seq <= _slot.pkt.seq:
                self.recvbuf.insert(i, slot)
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
        if pkt.seq > self.ack:
            self._save_packet(pkt, addr)
        elif pkt.seq < self.ack:
            logging.debug("Retransmission, dropping packet")
            pkt.data = bytes()
            return super()._ack(pkt, addr)

        old_ack = self.ack
        self._update_sack_options(pkt)

        # send ack
        sent = self._send(self._create_segment(), addr)

        if self.ack == old_ack:
            logging.debug("Packet out of order")
            pkt.data = bytes()

        return sent

    def read(self, bufsize):
        slot = self.pop_recv()
        if slot:
            return slot.pkt, slot.addr
        return super().read(bufsize)

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
        total_resent = 0
        for slot in self.window:
            self._send(slot.pkt, slot.addr)
            slot.nresent += 1
            total_resent += slot.nresent
            try:
                ack_segment, _ = self.read(0)
                self.refill_window(ack_segment)
            except TimeoutError:
                if total_resent == max_retries:
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
                # ack_segment, _ = self.read(0)
                ack_segment, _ = self.receive(0, ack=False, max_retries=10)
            except TimeoutError:
                # if no ACK arrives, resend all packets in the window, till
                # we get an ACK. If that doesn't work, raise ConnectionError
                self.resend_window(max_retries)
            return self.send(data, address)

        # the packet was sent, so wait for an ack without blocking
        try:
            ack_segment, _ = self.receive(0, ack=False)
            logging.debug(
                f"Received ack: {ack_segment.ack}, expected ack={self.window[0].pkt.expected_ack}"
            )
            if ack_segment.ack == self.window[0].pkt.expected_ack:
                self.nacks = 0
                self.window.pop(0)
            elif ack_segment.ack < self.seq:
                # refill window using the acknowledgement information in the sack blocks
                self.refill_window(ack_segment)
                self.nacks += 1
                # triple repeated ack, resend window
                if self.nacks == 3:
                    self.nacks = 0
                    self.resend_window()
        except TimeoutError:
            pass

        return bytes_sent

    def close(self):
        try:
            while self.window:
                self.resend_window()
        finally:
            super().close()


# class SelectiveAckTransport(RDTTransport):
#     def __init__(
#         self,
#         sock: socket.socket = None,
#         sock_timeout: float = None,
#         read_timeout: float = MIN_READ_TIMEOUT,
#     ):
#         super().__init__(sock, sock_timeout, read_timeout)
#         self.lock = threading.Lock()  # Lock for thread safety
#         self.window = []  # To store acknowledgment messages
#         self.window_size = 0

#     def send(self, data: bytes, address: sockaddr, max_retries=MAX_RETRIES) -> int:
#         seq = self.seq
#         ack = self.ack
#         if self.window_size > SACK_WINDOW_SIZE:
#             self.recv_ack()  # Can't send if the window is full
#             return 0

#         segment = self._create_segment(data, seq, ack)
#         bytes_sent = self.send_segment(segment, address)
#         return bytes_sent

#     def send_segment(self, segment, address):
#         print(f"sending with seq: {segment.seq}")
#         bytes_sent = self._send(segment, address)
#         self.add_to_buff(segment, address)
#         self.recv_ack()

#         self.check_timeout()
#         return bytes_sent

#     def has_full_window(self):
#         print(f"Window: {self.window_size} and max is:{SACK_WINDOW_SIZE} ")
#         print(self.window)
#         return self.window_size == SACK_WINDOW_SIZE

#     def update_window(self):
#         bytes_recv = self.recv_ack()

#         self.check_timeout()

#         return bytes_recv

#     def resend(self):
#         self.window[0].times_resent += 1
#         if self.window[0].times_resent > MAX_RETRIES:
#             raise ConnectionError("Connection lost")
#         self._send(self.window[0].segment, self.window[0].address)
#         self.window[0].time_sent = datetime.now()
#         self.recv_ack()

#     def recv_ack(self):
#         try:
#             ack_segment, _ = self.read(0)

#             logging.debug(f"Received ack: {ack_segment.ack}, expected ack={self.seq}")
#             print(f"Received ack: {ack_segment.ack}, expected ack={self.seq}")
#             return self.check_ack(ack_segment)
#         except TimeoutError:
#             print("No se recibio un ack")
#             return 0

#     def check_ack(self, ack_segment: RDTSegment):
#         print(f"Hay ack: {ack_segment.ack}")
#         for window_slot in self.window:
#             if window_slot.ack == ack_segment.ack:
#                 window_slot.has_ack = True
#                 print(f"Se recibio ack {window_slot}")
#                 break
#         bytes_recv = 0
#         while self.window_size and self.window[0].has_ack == True:
#             slot = self.window.pop(0)
#             self.window_size -= 1
#             bytes_recv += len(slot.segment.data)
#         return bytes_recv

#     def check_timeout(self):
#         if not self.window_size:
#             return
#         if datetime.now() - self.window[0].time_sent > ACK_WAIT_TIME:
#             print(f"reenvio {self.window[0].segment.seq}")
#             self.resend()

#     def update_with(self, pkt: RDTSegment):
#         if self.ack == pkt.seq:
#             self.ack += len(pkt.data)

#     def get_data_from_queue(self) -> bytes:
#         data_from_queue = bytes()
#         print(self.window)
#         for i in range(self.window_size):
#             if not self.window_size:
#                 break
#             for i, slot in enumerate(self.window):
#                 if slot.segment.seq == self.ack:
#                     data_from_queue += slot.segment.data
#                     self.ack += len(slot.segment.data)
#                     self.window.pop(i)
#                     self.window_size -= 1
#                     break
#         return data_from_queue

#     def add_to_buff(self, pkt: RDTSegment, address):
#         if pkt.seq < self.ack:
#             # ya se escribio, remandar ack por las dudas
#             self._ack(pkt)
#         self.window.append(WindowSlot(pkt, address, self.seq, datetime.now()))
#         self.window_size += 1

#     def get_window_size(self):
#         return self.window_size

#     # lado receiver
#     def receive(self, bufsize, max_retries=MAX_RETRIES):
#         pkt, addr = self.read(bufsize)
#         self._ack(pkt, addr)
#         if pkt.seq != self.ack:
#             # paquete desordenado
#             if any([segment.seq == pkt.seq for segment in self.window]):
#                 return None, addr
#             self.window.append(WindowRecv(pkt))
#         else:
#             self.ack += len(pkt.data)
#         return pkt, addr

#     def _ack(self, pkt: RDTSegment, addr: sockaddr):
#         logging.debug(
#             f"Received packet of length: {len(pkt.data)} seq: {pkt.seq}, expected seq={self.ack}"
#         )
#         self._send(self._create_segment(ack=pkt.seq + len(pkt.data)), addr)


# class WindowSlot:
#     def __init__(self, segment, address, ack, time_sent):
#         self.segment = segment
#         self.address = address
#         self.ack = ack
#         self.time_sent = time_sent
#         self.times_resent = 0
#         self.has_ack = False

#     def __str__(self):
#         return "Slot with seq: {} and is recv: {}".format(
#             self.segment.seq, self.has_ack
#         )

#     def __repr__(self):
#         return str(self)


# class WindowRecv:
#     def __init__(self, segment):
#         self.segment = segment
#         self.seq = segment.seq

#     def __str__(self):
#         return "Slot with seq: {}".format(self.seq)

#     def __repr__(self):
#         return str(self)
