# import logging
# import threading
# import time
# import os
# from pathlib import Path
# from src.lib.rdtp.transport import StopAndWaitTransport, sockaddr
# from src.lib.rdtp.server import FileTransferServer
# from src.lib.rdtp.operations import UploadOperation, run_operation

# from mininet.net import Mininet
# from mininet.topo import Topo


# class SingleSwitchTopo(Topo):
#     def __init__(self):
#         Topo.__init__(self)
#         # Add hosts and switches
#         server = self.addHost("h1")
#         cliente1 = self.addHost("h2")

#         # Add links
#         self.addLink(server, cliente1, loss=10)


# def upload(port, filepath: Path):
#     topo = SingleSwitchTopo()
#     net = Mininet(topo=topo, controller=None)
#     server = net.get("h1")
#     client = net.get("h2")
#     net.start()

#     server_command = f"venv/bin/python src/server -s server_storage -p {port}"
#     client_command = f"venv/bin/python src/upload -s {filepath.absolute()} -n {filepath.name} -q -H {server.IP()} -p {port}"

#     logging.info(server_command)
#     logging.info(client_command)
#     created_file = Path("server_storage", filepath.name)

#     try:
#         server.sendCmd(server_command)
#         logging.info("Starting client")

#         client.cmd(client_command)
#         logging.info("Finished client")
#         time.sleep(0.1)  # wait till the server saves the file
#         server.terminate()

#         assert created_file.exists()
#         assert created_file.stat().st_size == filepath.stat().st_size
#     finally:
#         # if created_file.exists():
#         #     created_file.unlink()
#         net.stop()


# def test_upload_small_file_mininet():
#     port = 23457
#     filepath = Path("tests", "files", "small.txt")
#     upload(port, filepath)


# def test_upload_medium_small_file_mininet():
#     port = 23458
#     filepath = Path("tests", "files", "medium_small.txt")
#     upload(port, filepath)
