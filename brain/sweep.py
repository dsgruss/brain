import json
import netifaces
import socket

from hostmodule import HostModule


def find_modules() -> list[HostModule]:
    """Implements a basic device discovery by simply scanning over a range of predetermined ports with the IDENTIFY directive and removing duplicates based on uuid."""

    res = []
    interfaces = []
    print("Discovering network interfaces...")
    for interface in netifaces.interfaces():
        interfaces_details = netifaces.ifaddresses(interface)
        if netifaces.AF_INET in interfaces_details:
            interfaces.extend(interfaces_details[netifaces.AF_INET])

    for interface in interfaces:
        print(f"Searching on {interface['addr']}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(1)
        # sock.bind((interface["addr"], port))

        for port in range(10000, 10020):
            sock.sendto(b"IDENTIFY", (interface["broadcast"], port))

        try:
            while True:
                msg, addr = sock.recvfrom(1500)
                if msg.startswith(b"IDENTIFY"):
                    continue
                parse = json.loads(msg)
                print(f"Got response from {addr}: {parse}")
                res.append(HostModule(parse["id"], addr[0], addr[1], interface["addr"]))

        except socket.timeout:
            pass

    i = 0
    seen = set()
    while i < len(res):
        if res[i].uuid not in seen:
            seen.add(res[i].uuid)
            i += 1
        else:
            del res[i]
    return res

if __name__ == "__main__":
    print(find_modules())