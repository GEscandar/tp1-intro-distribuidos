import socket
import logging
import select
import sys
from dataclasses import dataclass, astuple
from typing import Union, Tuple
from rdtp.exceptions import ConnectionError
from asyncio import DatagramTransport

MAX_RETRIES = 10
READ_TIMEOUT = 10.0
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
    SEQ_SIZE = 1

    """Size of the segment header in bytes"""
    HEADER_SIZE = SEQ_SIZE * 2

    def __init__(self, data: bytes = bytes(), seq: int = 0, ack: int = 0):
        self.data = data
        self.seq = seq
        self.ack = ack

    @staticmethod
    def unpack(data: bytes):
        seq = int.from_bytes(data[: RDTSegment.SEQ_SIZE], byteorder=sys.byteorder)
        data = data[RDTSegment.SEQ_SIZE :]

        ack = int.from_bytes(data[:1], byteorder=sys.byteorder)
        data = data[1:]

        return RDTSegment(data, seq, ack)

    def to_bytes(self):
        res = self.seq.to_bytes(RDTSegment.SEQ_SIZE, byteorder=sys.byteorder)
        res += self.ack.to_bytes(1, byteorder=sys.byteorder)
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

    def __init__(self, sock: socket.socket = None, timeout: float = None) -> None:
        if not sock:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if timeout is not None:
            sock.settimeout(timeout)
        self.sock = sock
        self.seq = 0
        self.ack = 0

    def __enter__(self, *args):
        return self

    def __exit__(self, *args):
        return self.sock.__exit__(*args)

    def _create_segment(self, data: bytes = None, seq: int = None, ack: int = None):
        data = data or bytes()
        seq = seq or self.seq
        ack = ack or self.ack
        return RDTSegment(data=data, seq=seq, ack=ack)

    def read(self, bufsize: int, wait=True):
        message, client_address = (None, None)
        ready = select.select([self.sock], [], [], READ_TIMEOUT if wait else 0)
        if ready[0]:
            message, client_address = self.sock.recvfrom(
                bufsize + RDTSegment.HEADER_SIZE
            )
        elif wait:
            raise TimeoutError

        return message, client_address

    def receive(self, bufsize, max_retries=MAX_RETRIES):
        """
        Receive data through the socket, stripping the headers.
        Emits the corresponding ACK to the sending end.
        """
        pkt, addr = None, None

        for i in range(max_retries + 1):
            try:
                data, addr = self.read(bufsize)
                pkt = RDTSegment.unpack(data)
                addr = sockaddr(*addr)
            except TimeoutError:
                if i == max_retries:
                    raise ConnectionError("Connection lost")
                logging.debug("got timeout receiving. retrying")
                continue

            if pkt.seq == self.ack:
                # if pkt.data:
                # got a non-empty data packet, send ack
                self.ack += len(pkt.data)
                ack_pkt = self._create_segment()
                logging.debug(f"got package. sending ACK. pkt=[{ack_pkt}]")
                print(f"got package. sending ACK to {addr}. pkt=[{ack_pkt}]")
                self.send(ack_pkt, addr)
                break

            logging.debug(f"Expecting remote seq={self.ack}. Got pkt=[{pkt}]")

            if pkt.seq < self.ack:
                # retransmission, resend ack
                self.send(self._create_segment(), addr)
        return pkt.data

    def send(self, segment: RDTSegment, address: sockaddr) -> int:
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
        logging.debug(
            f"Sent {bytes_sent} bytes to {address}, with data_len={data_len}, segment={data}"
        )
        print(
            f"Sent {bytes_sent} bytes to {address}, with data_len={data_len}, segment={data}"
        )
        if self.seq == segment.seq:
            # After sending, increment the seq number if this is not a retransmission
            self.seq += data_len
        return bytes_sent

    def close(self, wait=False):
        # Wait for resends due to lost outgoing acks
        # for i in range(MAX_RETRIES + 1):
        #     try:
        #         data, addr = self.read(1024)
        #         pkt = RDTSegment.unpack(data)
        #         addr = sockaddr(*addr)
        #         if not pkt.ack:
        #             pkt.ack = 1
        #             self.send(pkt, addr)
        #     except TimeoutError:
        #         if not wait:
        #             break
        #         continue

        logging.debug("Closing UDP socket")
        self.sock.close()


class StopAndWaitTransport(RDTTransport):
    def __init__(
        self, sock: socket.socket = None, timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        super().__init__(sock, timeout)

    def send(self, data: bytes, address: sockaddr, max_retries=MAX_RETRIES) -> int:
        seq = self.seq
        ack = self.ack
        for _ in range(max_retries + 1):
            try:
                super().send(
                    self._create_segment(data, seq, ack),
                    address,
                )
                ack_bytes, _ = self.read(1024)
                ack_segment = RDTSegment.unpack(ack_bytes)
                logging.debug(
                    f"Received ack: {ack_segment.ack}, expected ack={self.seq}"
                )
                print(f"Received ack: {ack_segment.ack}, expected ack={self.seq}")
                if ack_segment.ack != self.seq:
                    continue
                self.ack = ack_segment.ack
                return
            except TimeoutError:
                continue
        raise ConnectionError("Connection lost")
