import logging
import socket
from .operations import unpack_operation, UploadOperation
from .transport import RDTTransport, StopAndWaitTransport, RDTSegment, sockaddr


class ClientHandler:

    def __init__(self, transport: RDTTransport) -> None:
        self.op = None
        self.handler = None
        self.transport = transport

    def handle_upload(self):
        bytes_written = 0
        with open(self.op.destination, "wb") as f:
            while bytes_written < self.op.file_size:
                pkt = yield
                bytes_written += f.write(pkt.data)

    def on_receive(self, pkt: RDTSegment, addr: sockaddr):
        if not self.op:
            # only unpack the first time
            print(f"Operation data: {pkt.data}")
            self.op = unpack_operation(self.transport, pkt.data)
            print(f"Unpacked operation: {self.op.__dict__}")
            return

        if self.op.opcode == UploadOperation.opcode:
            if not self.handler:
                self.handler = self.handle_upload()
                self.handler.send(None)
            try:
                self.handler.send(pkt)
            except StopIteration:
                pass


class Server:
    """Asynchronous server for RDTP"""

    def __init__(self, port: int):
        self.address = sockaddr("", port)
        self.clients = {}
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(self.address.as_tuple())
        # we don't want this to block on read or write operations, so
        # set both timeouts to 0 or as close to it as possible
        self.transport = RDTTransport(sock, sock_timeout=0, read_timeout=0.1)

    def on_receive(self, pkt: RDTSegment, addr: sockaddr):
        self.clients[addr.as_tuple()]._ack(pkt, addr)

    def add_client(self, addr):
        self.clients[addr] = StopAndWaitTransport(sock=self.transport.sock)

    def start(self, wait=True):
        logging.info("Ready to receive connections")
        try:
            while True:
                try:
                    data, addr = self.transport.read(2048)
                    pkt = RDTSegment.unpack(data)
                    if addr not in self.clients:
                        self.add_client(addr)
                    self.on_receive(pkt, sockaddr(*addr))
                except TimeoutError:
                    if not wait:
                        break
                    continue
        except KeyboardInterrupt:
            logging.debug("Stopped by Ctrl+C")
        finally:
            self.transport.close()


class FileTransferServer(Server):
    def on_receive(self, pkt: RDTSegment, addr: sockaddr):
        client = self.clients[addr.as_tuple()]
        client.transport._ack(pkt, addr)
        client.on_receive(pkt, addr)

    def add_client(self, addr):
        self.clients[addr] = ClientHandler(
            transport=StopAndWaitTransport(sock=self.transport.sock)
        )
