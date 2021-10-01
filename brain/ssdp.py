import netifaces
import socket

def find_modules() -> list[tuple[str, str, int]]:
    MCAST_GRP = "239.255.255.250"
    MCAST_PORT = 1900

    request = b"M-SEARCH * HTTP/1.1\r\n"
    request += b"HOST: 239.255.255.250:1900\r\n"
    request += b'MAN: "ssdp:discover"\r\n'
    request += b"MX: 1\r\n"
    request += b"ST: upn:prompt-critical:control\r\n"
    request += b"\r\n"

    res = []  # (uuid, ip address, port)
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
                uuid = ""
                ip = ""
                port = 0
                for l in lines[1:]:
                    if l.startswith(b"LOCATION"):
                        url = l.split(b" ")[1]
                        loc = url.split(b"//")[1].split(b"/")[0]
                        ip = loc.split(b":")[0]
                        port = int(loc.split(b":")[1])
                    if l.startswith(b"USN"):
                        uuid = l.split(b"::")[0].split(b":")[-1]
                res.append((uuid, ip, port))

        except socket.timeout:
            pass

    i = 0
    seen = set()
    while i < len(res):
        if res[i][0] not in seen:
            seen.add(res[i][0])
            i += 1
        else:
            del res[i]
    return res

if __name__ == "__main__":
    print(find_modules())