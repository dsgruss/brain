import logging
import random
import socket
from typing import Optional

from brain.constants import PATCH_ADDR, PATCH_PORT
from brain.parsers import MessageParser
from brain.shared_proto import Directive


class InputJackListener:
    def __init__(self) -> None:
        self.connected = False

    def connect(self, address: str, mult_addr: str, port: int) -> None:
        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((address, port))
        self.sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            socket.inet_aton(mult_addr) + socket.inet_aton(address),
        )
        self.sock.setblocking(False)

        self.connected = True

    def disconnect(self):
        if self.connected:
            self.sock.close()
            self.connected = False

    def get_data(self) -> bytes:
        data = b""
        if self.connected:
            try:
                data = self.sock.recv(4096)
            except BlockingIOError:
                return b""
        return data


class OutputJackServer:
    def __init__(self, address) -> None:
        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

        # For now we just pick a random address in the multicast range for local testing purposes,
        # but ideally this will likely be some function of the interface address for devices that
        # all have their own ip (for instance, 10.0.42.69 => 239.42.69.(1, 2, ...)). Source-specific
        # multicast could help here.

        x, y, z = (
            random.randrange(0, 255),
            random.randrange(0, 255),
            random.randrange(0, 255),
        )
        mult_addr = f"239.{x}.{y}.{z}"
        self.endpoint = (mult_addr, random.randrange(49152, 65535))
        logging.info("Jack endpoint: " + str(self.endpoint) + " on " + address)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            socket.inet_aton(mult_addr) + socket.inet_aton(address),
        )

    def datagram_send(self, data: bytes):
        self.sock.sendto(data, self.endpoint)


class PatchServer:
    def __init__(self, uuid, bind_addr) -> None:
        self.uuid = uuid
        self.parser = MessageParser()

        # The socket allows address reuse, which may be a security concern. However, we are
        # exclusively looking at UDP multicasts in this protocol.

        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((bind_addr, PATCH_PORT))
        self.sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            socket.inet_aton(PATCH_ADDR) + socket.inet_aton(bind_addr),
        )
        self.sock.setblocking(False)

    def get_data(self) -> bytes:
        data = b""
        if self.sock is not None:
            try:
                data = self.sock.recv(4096)
            except BlockingIOError:
                return b""
        return data

    def message_send(self, message: Directive) -> None:
        logging.info("=> " + str((PATCH_ADDR, PATCH_PORT)) + ": " + str(message))
        payload = self.parser.create_directive(message)
        self.sock.sendto(payload, (PATCH_ADDR, PATCH_PORT))

    def get_message(self) -> Optional[Directive]:
        message = self.parser.parse_directive(self.get_data())
        if message is not None:
            logging.info("<= " + str(message))
        return message
