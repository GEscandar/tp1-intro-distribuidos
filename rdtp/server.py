import logging
import socket
from rdtp.transport import RDTTransport, StopAndWaitTransport, RDTSegment, sockaddr


class Server:

    def __init__(self, port: int):
        self.address = sockaddr("", port)
        self.clients = {}
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(self.address.as_tuple())
        # we don't want this to block on read or write operations, so
        # set both timeouts to 0
        self.transport = RDTTransport(sock, sock_timeout=0, read_timeout=0.1)

    def start(self, wait=True):
        logging.info("Ready to receive connections")
        try:
            while True:
                try:
                    data, addr = self.transport.read(2048)
                    if addr not in self.clients:
                        self.clients[addr] = StopAndWaitTransport()
                    self.clients[addr]._ack(RDTSegment.unpack(data), sockaddr(*addr))
                except TimeoutError:
                    if not wait:
                        break
                    continue
        except KeyboardInterrupt:
            logging.debug("Stopped by Ctrl+C")
        finally:
            self.transport.close()
