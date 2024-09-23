#!/usr/bin/python                                                                            
                                                                                             
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.link import TCLink
from mininet.node import RemoteController, Node

import threading


from rdtp.operations import UploadOperation, run_operation
from pathlib import Path


class SingleSwitchTopo(Topo):
    def __init__(self):
        Topo.__init__(self)
        # Add hosts and switches
        server = self.addHost('h1')
        cliente1 = self.addHost('h2')

        # Add links
        self.addLink(server, cliente1, loss=10)

def simpleTest():
    "Create and test a simple network"
    topo = SingleSwitchTopo()
    controller = RemoteController('c1')
    net = Mininet(topo=topo, controller=controller)
    net.start()
    print( "Dumping host connections" )
    dumpNodeConnections(net.hosts)

    server=net.get('h1')
    client = net.get('h2')

    port=23457
    filepath = Path("tests", "files", "small.txt")

    server_command = f"python3 -c \"from rdtp.server import FileTransferServer;server=FileTransferServer({port});server.start()\""
    client_command = f"python3 -c \"from rdtp.operations import UploadOperation, run_operation;run_operation({UploadOperation.opcode}, '{filepath.absolute()}', '{server.IP()}', {port}, '{filepath.name}')\""

    server.sendCmd(server_command)
    print("Starting client")

    client.cmdPrint(client_command)
    print("Finished client")
    server.terminate()
    net.stop()

if __name__ == '__main__':
    # Tell mininet to print useful information
    setLogLevel('info')
    simpleTest()