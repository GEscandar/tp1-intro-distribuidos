import socket
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


if __name__ == "__main__":
    from test import basic_server

    basic_server(*SERVER_ADDRESS)
