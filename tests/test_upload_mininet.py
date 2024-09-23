import logging
import threading
import time
import os
from pathlib import Path
from rdtp.transport import StopAndWaitTransport, sockaddr
from rdtp.server import FileTransferServer
from rdtp.operations import UploadOperation, run_operation

from mininet.net import Mininet
from mininet.topo import Topo


# codigo de: https://github.com/mininet/mininet/wiki/Introduction-to-Mininet#limits
class SingleSwitchTopo(Topo):
    def build(self, n=2):
        switch = self.addSwitch('s1')
        # Python's range(N) generates 0..N-1
        for h in range(n):
            host = self.addHost('h%s' % (h + 1))
            self.addLink(host, switch, loss=10)


def basic_server(server, server_command):
    logging.info("Starting server")
    return server.cmd(server_command)

def upload(port, filepath: Path):
    topo = SingleSwitchTopo(2)
    net = Mininet(topo=topo, controller=None)
    server = net.get('h1')
    client = net.get('h2')
    net.start()
    
    server_command = f"python3 -c \"from rdtp.server import FileTransferServer;server=FileTransferServer({port});server.start()\""
    client_command = f"python3 -c \"from rdtp.operations import UploadOperation, run_operation;run_operation({UploadOperation.opcode}, '{filepath.absolute()}', '{server.IP()}', {port}, '{filepath.name}')\""
    
    logging.info(server_command)
    logging.info(client_command)
    logging.info(client)
    created_file = Path(filepath.name)
    t = threading.Thread(target=basic_server, args=[server, server_command])
    try:
        
        t.start()
        res = client.cmd(client_command)
        logging.info("Finished client")
        time.sleep(0.1)  # wait till the server saves the file
        assert res == True
        assert created_file.exists()
        assert created_file.stat().st_size == filepath.stat().st_size
    finally:
        if t.is_alive():
            t.join()
        if created_file.exists():
            created_file.unlink()
        net.stop()


def test_upload_small_file_mininet():
    port = 23457
    filepath = Path("tests", "files", "small.txt")
    upload(port, filepath)


# def test_upload_medium_small_file_mininet():
#     addr = ("localhost", 23457)
#     filepath = Path("tests", "files", "medium_small.txt")
#     upload(addr, filepath)
