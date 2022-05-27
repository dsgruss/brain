import logging
import random
import selectors
import socket

from brain.constants import PATCH_PORT
from brain.parsers import Message, MessageParser


class InputJackListener:
    def __init__(self) -> None:
        self.sock = None

    def connect(self, address, port):
        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
        self.sock.setblocking(False)
        self.sock.bind((address, port))

    def get_data(self):
        data = None
        if self.sock is not None:
            try:
                data = self.sock.recv(2048)
            except BlockingIOError:
                return None
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
    def __init__(self, uuid, broadcast_addr, event_callback) -> None:
        self.uuid = uuid
        self.broadcast_addr = broadcast_addr
        self.event_callback = event_callback
        self.parser = MessageParser()

        # The socket allows address reuse, which may be a security concern. However, we are
        # exclusively looking at UDP broadcasts in this protocol.

        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
        self.sock.bind((self.broadcast_addr["addr"], PATCH_PORT))
        self.sock.setblocking(False)

        self.sel = selectors.DefaultSelector()
        self.sel.register(self.sock, selectors.EVENT_READ)

        super().__init__()

    def update(self):
        events = self.sel.select(timeout=0)
        for key, _ in events:
            self.datagram_received(key.fileobj.recv(2048))

    def message_send(self, message: Message):
        logging.info(
            "=> "
            + str((self.broadcast_addr["broadcast"], PATCH_PORT))
            + ": "
            + str(message)
        )
        payload = self.parser.create_directive(message)
        self.sock.sendto(payload, (self.broadcast_addr["broadcast"], PATCH_PORT))

    def datagram_received(self, data: bytes) -> None:
        logging.info("<= " + str(data.decode()))
        message = self.parser.parse_directive(data)
        if message is not None:
            self.event_callback(message)