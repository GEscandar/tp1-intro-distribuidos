import socket
import logging
import select
import sys
import errno
from dataclasses import dataclass, astuple
from .exceptions import ConnectionError

MAX_RETRIES = 100
MAX_READ_TIMEOUT = 1.0
MIN_READ_TIMEOUT = 0.01
DEFAULT_TIMEOUT = 2

__all__ = ["sockaddr", "RDTSegment", "RDTTransport", "StopAndWaitTransport"]


@dataclass
class sockaddr:
    """Representation of an IPv4 socket address"""

    host: str
    port: int

    def as_tuple(self):
        return astuple(self)


class RDTSegment:
    """An RDTP (Reliable Data Transfer Protocol) segment"""

    """Size of the sequence number in bytes"""
    SEQ_SIZE = 4

    """Size of the segment header in bytes"""
    HEADER_SIZE = SEQ_SIZE * 2 + 1

    def __init__(self, data: bytes = bytes(), seq: int = 0, ack: int = 0, op_metadata = False):
        self.data = data
        self.seq = seq
        self.ack = ack
        self.op_metadata = op_metadata

    @staticmethod
    def unpack(data: bytes):
        seq = int.from_bytes(data[: RDTSegment.SEQ_SIZE], byteorder=sys.byteorder)
        data = data[RDTSegment.SEQ_SIZE :]

        ack = int.from_bytes(data[: RDTSegment.SEQ_SIZE], byteorder=sys.byteorder)
        data = data[RDTSegment.SEQ_SIZE :]
        op_metadata = bool.from_bytes(data[: 1])
        data = data[1 :]

        return RDTSegment(data, seq, ack, op_metadata)

    def to_bytes(self):
        res = self.seq.to_bytes(RDTSegment.SEQ_SIZE, byteorder=sys.byteorder)
        res += self.ack.to_bytes(RDTSegment.SEQ_SIZE, byteorder=sys.byteorder)
        res += self.op_metadata.to_bytes(byteorder=sys.byteorder)
        res += self.data
        return res

    def __bytes__(self):
        return self.to_bytes()

    def __str__(self):
        return "seq: {}, ack: {}, len(data): {}".format(
            self.seq, self.ack, len(self.data)
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

    def _create_segment(self, data: bytes = None, seq: int = None, ack: int = None, op_metadata = False):
        data = data or bytes()
        seq = seq or self.seq
        ack = ack or self.ack
        return RDTSegment(data=data, seq=seq, ack=ack, op_metadata=op_metadata)

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

    def send(self, data: bytes, address: sockaddr, op_metadata=False, max_retries=MAX_RETRIES) -> int:
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
            # retransmission, don't return duplicate data to the receiving end
            logging.debug("Retransmission, discarding data")
            pkt.data = bytes()
        ack_pkt = self._create_segment()
        logging.debug(f"got package with seq={pkt.seq}, length={pkt_len}. sending ACK to {addr}. pkt=[{ack_pkt}]")
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
                logging.debug(f"Reading fd {self._sockfd}: {ready}")
                if ready[0]:
                    data, addr = self.sock.recvfrom(bufsize + RDTSegment.HEADER_SIZE)
                else:
                    raise TimeoutError("Socket read timed out")
            else:
                # this raises BlockingIOError if data is not yet available to read
                data, addr = self.sock.recvfrom(bufsize + RDTSegment.HEADER_SIZE)
            return RDTSegment.unpack(data), sockaddr(*addr)
        raise ConnectionError("Socket closed")

    def receive(self, bufsize, max_retries=0):
        """
        Receive data through the socket, stripping the headers.
        Emits the corresponding ACK to the sending end.
        """
        for i in range(max_retries+1):
            try:
                pkt, addr = self.read(bufsize)
                self._ack(pkt, addr)
                if i < 4 and self.read_timeout > 0.01:
                    self.read_timeout /= 2
                break
            except (TimeoutError, BlockingIOError):
                if i == max_retries:
                    raise
                elif (i-1) % 3 == 0 and self.read_timeout < MAX_READ_TIMEOUT:
                    self.read_timeout *= 2
                continue
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

    def send(self, data: bytes, address: sockaddr, op_metadata=False, max_retries=MAX_RETRIES) -> int:
        segment = self._create_segment(data, op_metadata=op_metadata)
        for nattempt in range(max_retries + 1):
            try:
                bytes_sent = self._send(
                    segment,
                    # self._create_segment(data, seq, ack),
                    address,
                )
                logging.debug("Waiting for ack...")
                ack_segment, _ = self.read(0)
                logging.debug(
                    f"Received ack: {ack_segment.ack}, expected ack={self.seq}, nattempt={nattempt}"
                )
                if ack_segment.ack != self.seq:
                    if (nattempt-1) % 3 == 0 and self.read_timeout < MAX_READ_TIMEOUT:
                        # triple retransmission, double read_timeout
                        self.read_timeout *= 2
                    continue
                elif nattempt < 4 and self.read_timeout > MIN_READ_TIMEOUT:
                    self.read_timeout /= 2
                # self.ack += len(data)
                return bytes_sent
            except (TimeoutError, BlockingIOError):
                continue
        raise ConnectionError("Connection lost")
