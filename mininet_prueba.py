#!/usr/bin/python
import argparse
import time

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.net import Mininet
from mininet.node import OVSController


def setup_topology(number_of_clients, packet_loss):
    net = Mininet(controller=OVSController, link=TCLink)

    info("*** Adding controller\n")
    net.addController("c0")

    info("*** Adding switch\n")
    s1 = net.addSwitch("s1")

    number_of_hosts = number_of_clients + 1
    hosts = [
        net.addHost(f"h{i}", ip=f"10.0.0.{i}") for i in range(1, number_of_hosts + 1)
    ]

    for i in range(0, number_of_hosts):
        net.addLink(hosts[i], s1, loss=packet_loss)

    info("*** Starting network\n")
    net.start()

    port = 4000

    info("*** Starting server on h1\n")
    hosts[0].cmd(
        f"venv/bin/python src/server -p {port} -s server_storage -H {hosts[0].IP()} > server.log 2>&1 &"
    )

    time.sleep(1)

    info("*** Starting clients in background\n")

    for i in range(1, number_of_hosts):
        hosts[i].cmd(
            f"venv/bin/python src/download -n medium.txt -d m{i}.txt -H {hosts[0].IP()} -p {port} > client{i}.log 2>&1 &"
        )

    CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mininet topology setup")
    parser.add_argument("--num-clients", type=int, default=3, help="Number of clients")
    parser.add_argument(
        "--packet-loss", type=int, default=10, help="Packet loss percentage"
    )

    args = parser.parse_args()

    setLogLevel("info")
    setup_topology(args.num_clients, args.packet_loss)
