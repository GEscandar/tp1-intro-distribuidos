#!/usr/bin/python
import argparse
import time

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.net import Mininet
from mininet.node import OVSController


def setup_topology(number_of_clients, packet_loss, operation):
    net = Mininet(controller=OVSController, link=TCLink)

    info("*** Adding controller\n")
    net.addController("c0")

    info("*** Adding switch\n")
    s1 = net.addSwitch("s1")

    number_of_hosts = number_of_clients + 1
    hosts = [
        net.addHost(f"h{i}", ip=f"10.0.0.{i}") for i in range(1, number_of_hosts + 1)
    ]

    info(f"*** Adding links with {packet_loss}% loss in server\n")
    net.addLink(hosts[0], s1, loss=packet_loss)
    for i in range(1, number_of_hosts):
        net.addLink(hosts[i], s1)

    info("*** Starting network\n")
    net.start()

    info("\n*** Testing network connectivity\n")
    net.pingAll()

    input("\nPress Enter to continue...\n")

    port = 4000

    info("*** Starting server on h1\n")
    hosts[0].cmd(
        f"xterm -e 'venv/bin/python src/server -p {port} -s server_storage -H {hosts[0].IP()}' &"
    )

    time.sleep(1)

    info("*** Starting clients in background\n")

    if operation == "download":
        for i in range(1, number_of_hosts):
            if i % 2 == 0:
                info(f"Starting client {i} with S&W\n")
                hosts[i].cmd(
                    f"xterm -e 'venv/bin/python src/download -n medium.txt -d m{i}.txt -H {hosts[0].IP()} -p {port}; bash' &"
                )
            else:
                info(f"Starting client {i} with SACK\n")
                hosts[i].cmd(
                    f"xterm -e 'venv/bin/python src/download -n medium.txt -d m{i}.txt -H {hosts[0].IP()} -p {port} --sack; bash' &"
                )
    elif operation == "upload":
        for i in range(1, number_of_hosts):
            if i % 2 == 0:
                info(f"Starting client {i} with S&W\n")
                hosts[i].cmd(
                    f"xterm -e 'venv/bin/python src/upload -n medium{i}.txt -s medium.txt -H {hosts[0].IP()} -p {port}; bash' &"
                )
            else:
                info(f"Starting client {i} with SACK\n")
                hosts[i].cmd(
                    f"xterm -e 'venv/bin/python src/upload -n medium{i}.txt -s medium.txt -H {hosts[0].IP()} -p {port} --sack; bash' &"
                )
    else:
        raise Exception("Invalid operation")

    CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mininet topology setup")
    parser.add_argument("--num-clients", type=int, default=4, help="Number of clients")
    parser.add_argument(
        "--packet-loss", type=int, default=10, help="Packet loss percentage"
    )
    parser.add_argument("--operation", type=str, default="download", help="Operation")

    args = parser.parse_args()

    setLogLevel("info")
    setup_topology(args.num_clients, args.packet_loss, args.operation)
