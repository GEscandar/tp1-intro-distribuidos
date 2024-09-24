from pathlib import Path
import socket
import select
from src.lib.rdtp.server import FileTransferServer

SERVER_ADDRESS = ("localhost", 12345)


def read(sock: socket.socket, bufsize: int, wait=True):
    message, client_address = (None, None)
    ready = select.select([sock], [], [], 10 if wait else 0)
    if ready[0]:
        message, client_address = sock.recvfrom(bufsize)
    elif wait:
        raise TimeoutError

    return message, client_address


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(SERVER_ADDRESS)
        s.setblocking(False)
        while True:
            data, addr = read(s, 1024, wait=False)
            if data:
                decoded = data.decode()
                print(f"Received data from {addr} => {decoded}")
                resp = decoded.upper().encode()
                s.sendto(resp, addr)


# ejemplo de cliente
# python3 -m rdtp upload -s tests/files/small.txt -n archi.txt -q -H 127.0.0.1 -p 12345
if __name__ == "__main__":
    print("Starting server")
    filepath = Path("server_storage")

    server = FileTransferServer(SERVER_ADDRESS[0], SERVER_ADDRESS[1], filepath)

    server.start()
