from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel

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
    net = Mininet(topo=topo, controller=None)
    net.start()
    print( "Dumping host connections" )
    dumpNodeConnections(net.hosts)

    server=net.get('h1')
    client = net.get('h2')

    port=23457
    filepath = Path("tests", "files", "small.txt")

    server_command = f"python3 src/server.py -s server_storage -H {server.IP()} -p {port}"
    client_command = f"python3 src/upload.py -s {filepath.absolute()} -n {filepath.name} -q -H {server.IP()} -p {port}"

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