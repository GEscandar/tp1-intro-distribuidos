import socket
import random
import sys
from server import SERVER_ADDRESS
import threading
from concurrent.futures import ThreadPoolExecutor
from src.lib.rdtp.transport import SelectiveAckTransport, StopAndWaitTransport, sockaddr
from testing_server import SERVER_ADDRESS
from concurrent.futures import ThreadPoolExecutor


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
            client_input = input("Enter something (or type 'fin' to quit): ")
            if client_input == "fin":
                done = True
                break
            try:
                resp = transport.send(client_input.encode(), sockaddr(*SERVER_ADDRESS))
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
        # resp = executor.map(sw_send, payloads[:4], payloads[4:8], payloads[8:12])
        resp = executor.map(sw_send, payloads[:4], payloads[4:8], payloads[8:12])
        resp = [val for tup in resp for val in tup]
    print(resp)
    # for s in resp:
    #     assert s.lower() in payloads


def tcp_sack_run():
    # resp = executor.map(sw_send, payloads[:4], payloads[4:8], payloads[8:12])

    with SelectiveAckTransport() as transport:
        transport.run()


#    resp = [val for tup in resp for val in tup]


if __name__ == "__main__":
    # test_concurrent_sending()

    # Get the arguments
    args = sys.argv

    if len(args) == 2:
        flag = args[1]
        # mejorar el tema de los flags (sacar 0 o 1 y poner algo tipo -s&w y -TCPsa)
        if flag == "0":
            sw_send()  # Stop & wait
        elif flag == "1":
            tcp_sack_run()  # TCP Selective Ack
    else:
        raise ("Invalid arguments")
