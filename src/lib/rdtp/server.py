import logging
import socket
import os
import sys
from pathlib import Path
from .operations import unpack_operation,UploadOperation,DownloadOperation,UPLOAD_CHUNK_SIZE,DOWNLOAD_CHUNK_SIZE
from .transport import RDTTransport, StopAndWaitTransport, SelectiveAckTransport, RDTSegment, sockaddr
from .exceptions import ConnectionError


class ClientOperationHandler:

    def __init__(self, transport: RDTTransport) -> None:
        self.op = None
        self.handler = None
        self.transport = transport
        self.addr = None

    def _init_handler(self, client_addr: sockaddr, storage_path: Path):
        self.addr = client_addr
        if self.op.opcode == UploadOperation.opcode:
            self.handler = self.handle_upload(storage_path)
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
                client_addr,
                max_retries=3,
            )
        

    def handle_upload(self, storage_path: Path):
        bytes_written = 0

        if not os.path.exists(storage_path):
            os.makedirs(storage_path)
        dest = Path(storage_path, self.op.destination)
        with open(dest, "wb") as f:
            while bytes_written < self.op.file_size:
                pkt = yield
                print(f"A punto de escribir secuencia {pkt.seq} y ack: {self.transport.ack} y seq: {self.transport.seq}")
                if (pkt.seq == self.transport.ack):
                    bytes_written += f.write(pkt.data)
                else:
                    self.transport.add_to_buff(pkt, self.addr)
                self.transport.update_with(pkt)
            logging.debug(f"Saving file {dest}")

    def handle_download(self, file_size):
        bytes_read = 0
        # chunk_size = DOWNLOAD_CHUNK_SIZE - RDTSegment.HEADER_SIZE
        chunk_size = DOWNLOAD_CHUNK_SIZE
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

    def on_receive(self, pkt: RDTSegment, addr: sockaddr, storage_path: Path):
        if not self.op:
            # only unpack the first time
            print(f"Operation data: {pkt.data}")
            self.op = unpack_operation(self.transport, pkt.data)
            print(f"Unpacked operation: {type(self.op)} - {self.op.__dict__}")
            self.transport.update_with(pkt)
            self._init_handler(addr, storage_path)
            return

        if self.op.opcode == UploadOperation.opcode:
            try:
                self.handler.send(pkt)
            except StopIteration:
                self.handler = None
                self.op = None


class Server:
    """Asynchronous server for RDTP"""

    def __init__(self, host: str, port: int, transport_factory=RDTTransport):
        self.address = sockaddr(host, port)
        self.clients = {}
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(self.address.as_tuple())
        # we don't want this to block on read or write operations, so
        # set both timeouts to 0 or as close to it as possible
        self.transport = transport_factory(sock, sock_timeout=0, read_timeout=0)

    def on_receive(self, pkt: RDTSegment, addr: sockaddr):
        pass

    def add_client(self, addr: sockaddr):
        self.clients[addr.as_tuple()] = SelectiveAckTransport(sock=self.transport.sock)

    def start(self):
        logging.info("Ready to receive connections")
        try:
            while True:
                try:
                    pkt, addr = self.transport.receive(4096)
                    if addr.as_tuple() not in self.clients:
                        self.add_client(addr)
                    self.on_receive(pkt, addr)
                except BlockingIOError:
                    continue
                except ConnectionError:
                    break
        except KeyboardInterrupt:
            logging.debug("Stopped by Ctrl+C")
        finally:
            logging.info("Server shutting down")
            self.close()

    def close(self):
        self.transport.close()


class FileTransferServer(Server):
    def __init__(
        self, host: str, port: int, path: Path, transport_factory=SelectiveAckTransport
    ):
        super().__init__(host, port, transport_factory)
        self.chunk_size = max(UPLOAD_CHUNK_SIZE, DOWNLOAD_CHUNK_SIZE)
        self.storage_path = path

    def on_receive(self, pkt: RDTSegment, addr: sockaddr):
        client = self.clients[addr.as_tuple()]
        client.transport._ack(pkt, addr)
        client.on_receive(pkt, addr, self.storage_path)

    def add_client(self, addr: sockaddr):
        self.clients[addr.as_tuple()] = ClientOperationHandler(
            transport=SelectiveAckTransport(sock=self.transport.sock)
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
                            client.transport.send(pending, sockaddr(*addr))
                    pkt, addr = self.transport.read(self.chunk_size)
                    print(f"Paquete: {pkt}")
                    if addr.as_tuple() not in self.clients:
                        self.add_client(addr)
                    try:
                        self.on_receive(pkt, addr)
                    except:
                        self.clients.pop(addr.as_tuple())
                except BlockingIOError:
                    continue
                except ConnectionError:
                    break
        except KeyboardInterrupt:
            logging.debug("Stopped by Ctrl+C")
        finally:
            logging.info("Server shutting down")
            self.close()
