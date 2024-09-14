import logging
import socket
from rdtp.transport import RDTTransport, RDTSegment, sockaddr


class Server:

    def __init__(self, port: int):
        self.address = sockaddr("", port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(self.address.as_tuple())
        # we don't want this to block on read, so pass timeout=0
        self.transport = RDTTransport(sock, timeout=0)

    def start(self):
        logging.info("Ready to receive connections")
        try:
            while True:
                try:
                    self.transport.receive(2048)
                    # data, address = self.transport.read(2048)
                except TimeoutError:
                    continue

                # segment = RDTSegment(data)

                # logging.debug("Client request coming from: " + str(address))
        except KeyboardInterrupt:
            logging.debug("Stopped by Ctrl+C")
        finally:
            self.transport.close()
