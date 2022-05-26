import asyncio
import logging

from brain.parsers import Message, MessageParser


class DataProtocol(asyncio.DatagramProtocol):
    def __init__(self, callback) -> None:
        self.callback = callback
        super().__init__()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        self.callback(data)


class PatchProtocol(asyncio.DatagramProtocol):
    def __init__(self, uuid, broadcast_addr, port, event_callback) -> None:
        self.uuid = uuid
        self.broadcast_addr = broadcast_addr
        self.port = port
        self.event_callback = event_callback
        self.parser = MessageParser()

        super().__init__()

    def connection_made(self, transport):
        logging.info("Patching broadcast connection made")
        self.transport = transport

    def message_send(self, message: Message):
        logging.info(
            "=> " + str((self.broadcast_addr, self.port)) + ": " + str(message)
        )
        payload = self.parser.create_directive(message)
        self.transport.sendto(payload, (self.broadcast_addr, self.port))

    def datagram_received(self, data: bytes, addr) -> None:
        logging.info("<= " + str(data.decode()))
        message = self.parser.parse_directive(data)
        if message is not None:
            self.event_callback(message)
