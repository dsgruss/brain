import socket

sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
sock.bind(("10.0.0.2", 59701))
sock.settimeout(0.5)

while True:
    try:
        data, addr = sock.recvfrom(1024)
        sock.sendto(data, ("10.0.0.2", 59702))
    except socket.timeout:
        pass