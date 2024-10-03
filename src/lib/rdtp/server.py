import logging
import socket
import os
import sys
import threading
import queue
from pathlib import Path
from typing import Dict, List
from .operations import (
    unpack_operation,
    UploadOperation,
    DownloadOperation,
)
from .transport import (
    RDTTransport,
    StopAndWaitTransport,
    SACKTransport,
    RDTSegment,
    sockaddr,
    RECV_CHUNK_SIZE,
)
from .exceptions import ConnectionError

SERVER_READ_TIMEOUT = 0.001


def get_server_socket(addr: sockaddr):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(addr.as_tuple())
    return sock


class ClientOperationHandler(threading.Thread):

    def __init__(
        self,
        transport_factory,
        client_addr: sockaddr,
        storage_path: Path,
    ) -> None:
        threading.Thread.__init__(self)
        logging.info(f"Starting client handler for {client_addr}")
        self.op = None
        self.handler = None
        self.transport = transport_factory(
            sock=get_server_socket(sockaddr("", 0)),
            sock_timeout=0,
            read_timeout=SERVER_READ_TIMEOUT,
        )
        self.finished = False
        self.client_addr = client_addr
        self.storage_path = storage_path
        self.lock = threading.Lock()
        self.queue = queue.Queue()

    def _enqueue(self, pkt: RDTSegment):
        self.queue.put(pkt)

    def _init_handler(self):
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)
        if self.op.opcode == UploadOperation.opcode:
            self.handler = self.handle_upload()
            self.handler.send(None)
        elif self.op.opcode == DownloadOperation.opcode:
            self.op.filename = str(Path(self.storage_path, self.op.filename))
            file_size = os.stat(self.op.filename).st_size
            self.handler = self.handle_download(file_size)
            logging.debug(f"Sending file size of {file_size} to client")
            # send file size to client without waiting too long for the ack
            self.transport.send(
                file_size.to_bytes(4, sys.byteorder), self.client_addr
            )

    def handle_upload(self):
        bytes_written = 0
        dest = Path(self.storage_path, self.op.destination)
        logging.info(f"Starting upload of file at {dest}")
        with open(dest, "wb") as f:
            while bytes_written < self.op.file_size:
                pkt = yield
                logging.debug(f"Writing packet {pkt} to file")
                bytes_written += f.write(pkt.data)
            logging.info(f"Upload end, saving file {dest}")

    def handle_download(self, file_size):
        bytes_read = 0
        logging.info(f"Starting download of file at {self.op.filename}")
        chunk_size = RECV_CHUNK_SIZE
        with open(self.op.filename, "rb") as f:
            while bytes_read < file_size:
                content = f.read(chunk_size)
                logging.debug(f"yielding chunk: {bytes_read}")
                bytes_read += chunk_size
                yield content
            logging.info(f"Download end, closing file {self.op.filename}")

    def get_pending(self):
        content = None
        if self.op and self.op.opcode == DownloadOperation.opcode:
            try:
                content = next(self.handler)
            except StopIteration:
                self.handler = None
                self.op = None
                self.finished = True
        return content

    def on_receive(self, pkt: RDTSegment, addr: sockaddr):
        if not self.op:
            if pkt.op_metadata:
                # only unpack the first time
                logging.debug(f"Operation data: {pkt.data}")
                self.op = unpack_operation(self.transport, pkt.data)
                logging.debug(
                    f"Unpacked operation: {type(self.op)} - {self.op.__dict__}"
                )
                self._init_handler()
            return
        elif self.op.opcode == UploadOperation.opcode:
            try:
                self.handler.send(pkt)
            except StopIteration:
                self.handler = None
                self.op = None
                self.finished = True

    def run(self):
        try:
            while not self.finished:
                try:
                    pending = self.get_pending()
                    if pending:
                        self.transport.send(pending, self.client_addr)
                    pkt, _ = self.transport.read(RECV_CHUNK_SIZE)
                    self.transport._ack(pkt, self.client_addr)
                    self.on_receive(pkt, self.client_addr)
                except (TimeoutError, BlockingIOError):
                    try:
                        pkt = self.queue.get(block=False)
                        # this is a handshake message, so simply acknowledge it
                        self.transport._ack(pkt, self.client_addr)
                    except queue.Empty:
                        pass
                    continue
                except ConnectionError:
                    logging.error("Connection error, closing server")
                    break
                except Exception as e:
                    logging.error(f"Error running client handler: {e}")
                    break
        finally:
            # logging.debug("Closing client handler, for some reason")
            self.close()

    def close(self):
        if not self.finished:
            self.finished = True
        with self.lock:
            logging.info(f"Closing client handler for {self.client_addr}")
            self.transport.close()


class Server:
    """Asynchronous server for RDTP"""

    def __init__(self, host: str, port: int, transport_factory=RDTTransport):
        self.address = sockaddr(host, port)
        self.clients = {}
        # we don't want this to block on read or write operations, so
        # set both timeouts to 0 or as close to it as possible
        self.transport_factory = transport_factory
        self.transport = transport_factory(
            sock=get_server_socket(self.address),
            sock_timeout=0,
            read_timeout=1,
        )

    def on_receive(self, pkt: RDTSegment, addr: sockaddr):
        pass

    def add_client(self, addr: sockaddr):
        self.clients[addr.as_tuple()] = self.transport_factory(
            sock=self.transport.sock
        )

    def start(self):
        logging.info("Ready to receive connections")
        try:
            while True:
                try:
                    pkt, addr = self.transport.receive(4096)
                    if addr.as_tuple() not in self.clients:
                        self.add_client(addr)
                    self.on_receive(pkt, addr)
                except (TimeoutError, BlockingIOError):
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
        self,
        host: str,
        port: int,
        path: Path,
        transport_factory=StopAndWaitTransport,
    ):
        super().__init__(host, port, transport_factory)
        self.chunk_size = RECV_CHUNK_SIZE
        self.storage_path = path
        self.client_threads: Dict[sockaddr, ClientOperationHandler] = {}
        self.finished_threads: List[ClientOperationHandler] = []
        self.clients_lock = threading.Lock()

    def start(self):
        logging.info("Listening for incoming connections")
        try:
            while True:
                try:
                    pkt, addr = self.transport.read(self.chunk_size)
                    with self.clients_lock:
                        if addr.as_tuple() not in self.client_threads:
                            logging.debug(
                                f"Adding client handler... => {self.clients}"
                            )
                            client = ClientOperationHandler(
                                transport_factory=self.transport_factory,
                                client_addr=addr,
                                storage_path=self.storage_path,
                            )
                            self.client_threads[addr.as_tuple()] = client
                            client.start()
                        else:
                            self.client_threads[addr.as_tuple()]._enqueue(pkt)
                        for client_addr in list(self.client_threads.keys()):
                            client = self.client_threads[client_addr]
                            if client.finished:
                                logging.debug(f"Popping client: {client_addr}")
                                try:
                                    self.finished_threads.append(
                                        self.client_threads.pop(client_addr)
                                    )
                                except KeyError:
                                    pass
                except (TimeoutError, BlockingIOError):
                    continue
                except ConnectionError:
                    logging.error("Connection error, closing server")
                    break
        except KeyboardInterrupt:
            logging.debug("Stopped by Ctrl+C")
        except Exception as e:
            logging.error(e)
        finally:
            self.close()

    def close(self):
        logging.info("Server shutting down")
        with self.clients_lock:
            for client in self.finished_threads:
                client.join()
            for _, client in self.client_threads.items():
                client.close()
                client.join()
        super().close()
