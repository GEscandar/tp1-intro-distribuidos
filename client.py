import socket
import random
from server import SERVER_ADDRESS
import threading
from concurrent.futures import ThreadPoolExecutor
from rdtp.transport import StopAndWaitTransport, sockaddr


def client_send(*things):
    done = False
    res = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        while True:
            for t in things:
                try:
                    if t == "fin":
                        done = True
                        break
                    s.sendto(t.encode(), SERVER_ADDRESS)
                    resp = s.recv(1024).decode()
                    res.append(resp)
                except KeyboardInterrupt:
                    continue
            return tuple(res)


def sw_send(*things):
    res = []
    with StopAndWaitTransport() as transport:
        while True:
            for t in things:
                try:
                    if t == "fin":
                        done = True
                        break
                    resp = transport.send(t.encode(), sockaddr(*SERVER_ADDRESS))
                    res.append(resp)
                except KeyboardInterrupt:
                    continue
            return tuple(res)


def test_concurrent_sending():
    payloads = [
        "arg1",
        "arg2",
        "arg3",
        "fin",
        "arg4",
        "arg5",
        "arg6",
        "fin",
        "arg7",
        "arg8",
        "arg9",
        "fin",
    ]
    with ThreadPoolExecutor() as executor:
        resp = executor.map(sw_send, payloads[:4], payloads[4:8], payloads[8:12])
        resp = [val for tup in resp for val in tup]
    print(resp)
    # for s in resp:
    #     assert s.lower() in payloads


if __name__ == "__main__":
    test_concurrent_sending()
