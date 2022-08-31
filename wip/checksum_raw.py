import socket
import time
from scapy.all import IFACES, conf

full_sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
full_sock.bind(("10.0.0.2", 19992))
for _ in range(0, 2):
# while True:
    full_sock.sendto(b'{"Halt":{"uuid":"GLOBA0"}}', ("239.0.0.0", 19874))

    IFACES.show()
    iface = IFACES.dev_from_index(4)
    raw_sock = conf.L2socket(iface=iface)
    raw_sock.send(bytes.fromhex(
    "   01 00 5e 00 00 00 f0 2f 74 1a c8 8e 08 00 45 00" \
    "   00 36 36 39 00 00 01 11 8a 7c 0a 00 00 02 ef 00" \
    "   00 00 4e 18 4d a2 00 22 22 0d 7b 22 48 61 6c 74" \
    "   22 3a 7b 22 75 75 69 64 22 3a 22 47 4c 4f 42 41" \
    "   31 22 7d 7d"))

    # Header Checksum bad
    raw_sock.send(bytes.fromhex(
    "   01 00 5e 00 00 00 f0 2f 74 1a c8 8e 08 00 45 00" \
    "   00 36 36 39 00 00 01 11 8a 70 0a 00 00 02 ef 00" \
    "   00 00 4e 18 4d a2 00 22 22 0d 7b 22 48 61 6c 74" \
    "   22 3a 7b 22 75 75 69 64 22 3a 22 47 4c 4f 42 41" \
    "   32 22 7d 7d"))

    # UDP Checksum bad
    raw_sock.send(bytes.fromhex(
    "   01 00 5e 00 00 00 f0 2f 74 1a c8 8e 08 00 45 00" \
    "   00 36 36 39 00 00 01 11 8a 7c 0a 00 00 02 ef 00" \
    "   00 00 4e 18 4d a2 00 22 22 00 7b 22 48 61 6c 74" \
    "   22 3a 7b 22 75 75 69 64 22 3a 22 47 4c 4f 42 41" \
    "   33 22 7d 7d"))

    # Both Checksum bad
    raw_sock.send(bytes.fromhex(
    "   01 00 5e 00 00 00 f0 2f 74 1a c8 8e 08 00 45 00" \
    "   00 36 36 39 00 00 01 11 8a 70 0a 00 00 02 ef 00" \
    "   00 00 4e 18 4d a2 00 22 22 00 7b 22 48 61 6c 74" \
    "   22 3a 7b 22 75 75 69 64 22 3a 22 47 4c 4f 42 41" \
    "   34 22 7d 7d"))
    time.sleep(1)
