import logging
import random
import socket
from typing import Union

from brain.constants import PATCH_PORT
from brain.parsers import Message, MessageParser


class InputJackListener:
    def __init__(self) -> None:
        self.connected = False

    def connect(self, address: str, port: int) -> None:
        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
        self.sock.setblocking(False)
        self.sock.bind((address, port))
        self.connected = True

    def disconnect(self):
        if self.connected:
            self.sock.close()
            self.connected = False

    def get_data(self) -> bytes:
        data = b""
        if self.connected:
            try:
                data = self.sock.recv(2048)
            except BlockingIOError:
                return b""
        return data


class OutputJackServer:
    def __init__(self, address) -> None:
        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

        # For now we just pick a port, but this should be negotiated during device discovery
        self.endpoint = (address, random.randrange(49152, 65535))
        logging.info("Jack endpoint: " + str(self.endpoint))

    def datagram_send(self, data: bytes):
        self.sock.sendto(data, self.endpoint)


class PatchServer:
    def __init__(self, uuid, bind_addr, broadcast_addr) -> None:
        self.uuid = uuid
        self.broadcast_addr = broadcast_addr
        self.parser = MessageParser()

        # The socket allows address reuse, which may be a security concern. However, we are
        # exclusively looking at UDP broadcasts in this protocol.

        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
        self.sock.bind((bind_addr, PATCH_PORT))
        self.sock.setblocking(False)

    def get_data(self) -> bytes:
        data = b""
        if self.sock is not None:
            try:
                data = self.sock.recv(2048)
            except BlockingIOError:
                return b""
        return data

    def message_send(self, message: Message) -> None:
        logging.info(
            "=> " + str((self.broadcast_addr, PATCH_PORT)) + ": " + str(message)
        )
        payload = self.parser.create_directive(message)
        self.sock.sendto(payload, (self.broadcast_addr, PATCH_PORT))

    def get_message(self) -> Union[Message, None]:
        message = self.parser.parse_directive(self.get_data())
        if message is not None:
            logging.info("<= " + str(message))
        return message
