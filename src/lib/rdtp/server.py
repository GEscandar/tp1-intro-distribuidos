import logging
import os
from pathlib import Path
import socket
from .operations import unpack_operation, UploadOperation
from .transport import RDTTransport, StopAndWaitTransport, RDTSegment, sockaddr
import select

SERVER_ADDRESS = ("localhost", 12345)


def read(sock: socket.socket, bufsize: int, wait=True):
    message, client_address = (None, None)
    ready = select.select([sock], [], [], 10 if wait else 0)
    if ready[0]:
        message, client_address = sock.recvfrom(bufsize)
    elif wait:
        raise TimeoutError

    return message, client_address


class ClientHandler:

    def __init__(self, transport: RDTTransport) -> None:
        self.op = None
        self.handler = None
        self.transport = transport

    def handle_upload(self, storage_path: Path):
        bytes_written = 0

        if not os.path.exists(storage_path):
            os.makedirs(storage_path)
        with open(Path(storage_path, self.op.destination), "wb") as f:
            while bytes_written < self.op.file_size:
                pkt = yield
                bytes_written += f.write(pkt.data)
            logging.debug(f"Saving file {self.op.destination}")

    def on_receive(self, pkt: RDTSegment, addr: sockaddr, storage_path: Path):
        if not self.op:
            # only unpack the first time
            print(f"Operation data: {pkt.data}")
            self.op = unpack_operation(self.transport, pkt.data)
            print(f"Unpacked operation: {self.op.__dict__}")
            return

        if self.op.opcode == UploadOperation.opcode:
            if not self.handler:
                self.handler = self.handle_upload(storage_path)
                self.handler.send(None)
            try:
                self.handler.send(pkt)
            except StopIteration:
                pass


class Server:
    """Asynchronous server for RDTP"""

    def __init__(self, host: str, port: int):
        self.address = sockaddr(host, port)
        self.clients = {}
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(self.address.as_tuple())
        # we don't want this to block on read or write operations, so
        # set both timeouts to 0 or as close to it as possible
        self.transport = RDTTransport(sock, sock_timeout=0, read_timeout=0.01)

    def on_receive(self, pkt: RDTSegment, addr: sockaddr):
        self.clients[addr.as_tuple()]._ack(pkt, addr)

    def add_client(self, addr: sockaddr):
        self.clients[addr.as_tuple()] = StopAndWaitTransport(sock=self.transport.sock)

    def start(self):
        logging.info("Ready to receive connections")
        try:
            while True:
                try:
                    pkt, addr = self.transport.read(2048)
                    if addr.as_tuple() not in self.clients:
                        self.add_client(addr)
                    self.on_receive(pkt, addr)
                except TimeoutError:
                    continue
        except KeyboardInterrupt:
            logging.debug("Stopped by Ctrl+C")
        finally:
            logging.debug("Server shutting down")
            self.close()

    def close(self):
        self.transport.close()


class FileTransferServer(Server):
    def __init__(self, host: str, port: int, path: Path):
        # Call the parent class's __init__ method
        super().__init__(host, port)
        self.storage_path = path

    def on_receive(self, pkt: RDTSegment, addr: sockaddr):
        client = self.clients[addr.as_tuple()]
        client.transport._ack(pkt, addr)
        client.on_receive(pkt, addr, self.storage_path)

    def add_client(self, addr: sockaddr):
        self.clients[addr.as_tuple()] = ClientHandler(
            transport=StopAndWaitTransport(sock=self.transport.sock)
        )
