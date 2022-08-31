import time
from scapy.all import *
import scapy.contrib.igmp

p = IP(src="10.0.0.4", dst="224.0.0.1")/scapy.contrib.igmp.IGMP()
IFACES.show()
iface = IFACES.dev_from_index(4)

while True:
    send(p, iface=iface)
    time.sleep(240)