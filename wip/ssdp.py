import netifaces
import socket
import struct
import time

from hostmodule import HostModule


def find_modules() -> list[HostModule]:
    """Performs a multicast broadcast on all interfaces and returns all the unique devices found."""
    MCAST_GRP = "239.255.255.250"
    MCAST_PORT = 1900

    request = b"M-SEARCH * HTTP/1.1\r\n"
    request += b"HOST: 239.255.255.250:1900\r\n"
    request += b'MAN: "ssdp:discover"\r\n'
    request += b"MX: 1\r\n"
    request += b"ST: upn:prompt-critical:control\r\n"
    request += b"\r\n"

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
        for port in range(2000, 2010):
            try:
                sock.bind((interface["addr"], port))
                break
            except OSError:
                continue
        else:
            print("Unable to find open port.")
            exit(-1)

        sock.sendto(request, (MCAST_GRP, MCAST_PORT))

        try:
            while True:
                msg, addr = sock.recvfrom(10240)
                print(msg)
                lines = msg.split(b"\r\n")
                if b"200" not in lines[0]:
                    continue
                val = HostModule("", "", 0, interface["addr"])
                for l in lines[1:]:
                    if l.startswith(b"LOCATION"):
                        url = l.split(b" ")[1]
                        loc = url.split(b"//")[1].split(b"/")[0]
                        val.address = loc.split(b":")[0]
                        val.port = int(loc.split(b":")[1])
                    if l.startswith(b"USN"):
                        val.uuid = l.split(b"::")[0].split(b":")[-1]
                res.append(val)

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


def ssdp_client_thread(local_address, directive_port, uuid):
    """Thread that responds to SSDP searches."""
    mcast_group = "239.255.255.250"
    mcast_port = 1900
    sent_time = 0
    notify_ttl = 3600

    ssdp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    ssdp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
    ssdp_sock.bind((local_address, mcast_port))
    mreq = struct.pack("4sl", socket.inet_aton(mcast_group), socket.INADDR_ANY)
    ssdp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    resp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    for port in range(2000, 2010):
        try:
            resp_sock.bind((local_address, port))
            break
        except OSError:
            continue
    else:
        print(f"Unable to find open port on {local_address}.")
        exit(-1)
    resp_sock.settimeout(1)

    notify = "NOTIFY * HTTP/1.1\r\n"
    notify += f"HOST: {mcast_group}:{mcast_port}\r\n"
    notify += f"CACHE-CONTROL: max-age={notify_ttl}\r\n"
    notify += f"LOCATION: udp://{local_address}:{directive_port}/\r\n"
    notify += "NT: urn:prompt-critical:control\r\n"
    notify += "NTS: ssdp:alive\r\n"
    notify += "SERVER: Prompt-Critical/0.1\r\n"
    notify += f"USN: uuid:{uuid}::urn:prompt-critical:control\r\n"
    notify += "\r\n"

    search_res = "HTTP/1.1 200 OK\r\n"
    search_res += "ST: urn:prompt-critical:control\r\n"
    search_res += f"LOCATION: udp://{local_address}:{directive_port}/\r\n"
    search_res += "SERVER: Prompt-Critical/0.1\r\n"
    search_res += f"CACHE-CONTROL: max-age={notify_ttl}\r\n"
    search_res += f"USN: uuid:{uuid}::urn:prompt-critical:control\r\n"
    search_res += "\r\n"

    while True:
        if (time.time() - sent_time) > notify_ttl:
            print(f"Sending SSDP notification on {local_address}.")
            resp_sock.sendto(bytes(notify, "ASCII"), (mcast_group, mcast_port))
            sent_time = time.time()
        try:
            msg, addr = ssdp_sock.recvfrom(10240)
            res = msg.split(b"\r\n")
            if not res[0].startswith(b"M-SEARCH"):
                continue
            if b"ST: upn:prompt-critical:control" not in res:
                continue
            print(res, addr, local_address)
            resp_sock.sendto(bytes(search_res, "ASCII"), addr)
        except socket.timeout:
            continue


if __name__ == "__main__":
    print(find_modules())
