import socket
import time

sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
sock.bind(("10.0.0.2", 59702))
sock.settimeout(0.5)

while True:
    result = []
    for _ in range(1000):
        t = time.perf_counter()
        sock.sendto(b"test", ("10.0.0.2", 59701))
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            continue
        result.append((time.perf_counter() - t) * 1000)
    print(sum(result) / 1000, len(result))
    time.sleep(1)