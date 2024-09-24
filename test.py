from src.lib.rdtp.transport import StopAndWaitTransport, sockaddr
from src.lib.rdtp.server import Server


def basic_server(host, port):
    print("Starting server")
    server = Server(port)
    server.start()
    # with RDTTransport() as server:
    #     server.sock.bind((host, port))
    #     while True:
    #         try:
    #             server.receive(1024)
    #         except TimeoutError:
    #             continue


def test_base_send():
    print("Hello world!")
    client = StopAndWaitTransport()
    addr = ("localhost", 12345)
    # t = threading.Thread(target=basic_server, args=addr)
    # p = mp.Process(target=basic_server, args=addr)
    # try:
    #     t.start()
    client.send(b"aaa", sockaddr(*addr))
    print("Sent!")
    # finally:
    #     t.join()
    # p.close()


if __name__ == "__main__":
    test_base_send()
