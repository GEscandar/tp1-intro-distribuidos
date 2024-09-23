import logging
import socket
import os
import sys
from .operations import unpack_operation, UploadOperation, DownloadOperation
from .transport import RDTTransport, StopAndWaitTransport, RDTSegment, sockaddr


class ClientOperationHandler:

    def __init__(self, transport: RDTTransport, client_addr: sockaddr) -> None:
        self.op = None
        self.handler = None
        self.client_addr = client_addr
        self.transport = transport

    def _init_handler(self):
        if self.op.opcode == UploadOperation.opcode:
            self.handler = self.handle_upload()
            self.handler.send(None)
        elif self.op.opcode == DownloadOperation.opcode:
            file_size = os.stat(self.op.filename).st_size
            print("file size: ", file_size)
            self.handler = self.handle_download(file_size)
            print("Sending file size to client")
            logging.debug("Sending file size to client")
            # send file size to client without waiting too long for the ack
            self.transport.send(
                file_size.to_bytes(4, sys.byteorder),
                self.client_addr,
                max_retries=3,
            )

    def handle_upload(self):
        bytes_written = 0
        with open(self.op.destination, "wb") as f:
            while bytes_written < self.op.file_size:
                pkt = yield
                bytes_written += f.write(pkt.data)
            logging.debug(f"Saving file {self.op.destination}")

    def handle_download(self, file_size):
        bytes_read = 0
        chunk_size = 4096 - RDTSegment.HEADER_SIZE
        with open(self.op.filename, "rb") as f:
            while bytes_read < file_size:
                yield f.read(chunk_size)
                bytes_read += chunk_size

    def get_pending(self):
        content = None
        if self.op and self.op.opcode == DownloadOperation.opcode:
            try:
                content = next(self.handler)
            except StopIteration:
                self.handler = None
                self.op = None
        return content

    def on_receive(self, pkt: RDTSegment, addr: sockaddr):
        if not self.op:
            # only unpack the first time
            print(f"Operation data: {pkt.data}")
            self.op = unpack_operation(self.transport, pkt.data)
            print(f"Unpacked operation: {type(self.op)} - {self.op.__dict__}")
            self._init_handler()
            return

        if self.op.opcode == UploadOperation.opcode:
            try:
                self.handler.send(pkt)
            except StopIteration:
                self.handler = None
                self.op = None


class Server:
    """Asynchronous server for RDTP"""

    def __init__(self, port: int, transport_factory=RDTTransport):
        self.address = sockaddr("", port)
        self.clients = {}
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(self.address.as_tuple())
        # we don't want this to block on read or write operations, so
        # set both timeouts to 0 or as close to it as possible
        self.transport = transport_factory(sock, sock_timeout=0, read_timeout=0.01)

    def on_receive(self, pkt: RDTSegment, addr: sockaddr):
        pass

    def add_client(self, addr: sockaddr):
        self.clients[addr.as_tuple()] = StopAndWaitTransport(sock=self.transport.sock)

    def start(self):
        logging.info("Ready to receive connections")
        try:
            while True:
                try:
                    pkt, addr = self.transport.receive(4096, max_retries=0)
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
    def __init__(self, port: int, transport_factory=StopAndWaitTransport):
        super().__init__(port, transport_factory)

    def on_receive(self, pkt: RDTSegment, addr: sockaddr):
        client = self.clients[addr.as_tuple()]
        client.on_receive(pkt, addr)

    def add_client(self, addr: sockaddr):
        self.clients[addr.as_tuple()] = ClientOperationHandler(
            transport=StopAndWaitTransport(sock=self.transport.sock), client_addr=addr
        )

    def start(self):
        logging.info("Ready to receive connections")
        try:
            while True:
                try:
                    # check for pending download sends
                    for addr, client in self.clients.items():
                        pending = client.get_pending()
                        if pending:
                            self.transport.send(pending, sockaddr(*addr))
                    pkt, addr = self.transport.receive(4096, max_retries=0)
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
