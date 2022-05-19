import asyncio
import netifaces
import json
import socket
import uuid

from enum import Enum
from itertools import chain


class Jack:
    def __init__(self, parent_module):
        self.state = False
        self.parent_module = parent_module

    def patch_enabled(self, state: bool):
        # Indicate the jack is available for patching and notify other modules
        if self.state != state:
            self.state = state
            self.parent_module.update_patch()

    def is_patched(self) -> bool:
        # Returns True if this jack is connected to another one
        return False

    def clear(self):
        # Disconnect this jack from all other modules
        pass


class InputJack(Jack):
    def __init__(self, parent_module, data_callback, **kwargs):
        self.callback = data_callback
        self.params = kwargs
        super().__init__(parent_module)


class OutputJack(Jack):
    def __init__(self, parent_module, **kwargs):
        self.params = kwargs
        self.destinations = []
        super().__init__(parent_module)

    def send(self, data: bytes):
        rtp_header = bytes("############", "ASCII")
        for loc in self.destinations:
            self.parent_module._sock.sendto(rtp_header + data, loc)


class Module:
    # Class to handle networking and discovery layers for each module
    inputs = []
    outputs = []
    patch_port = 19874

    def __init__(self, name, patching_callback=None):
        # Initializes the module and allows for discovery by management requests
        self.name = name
        self.patching_callback = patching_callback
        self.uuid = str(uuid.uuid4())
        self.patch_state = PatchState.IDLE

        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
        self.sock.bind(("", self.patch_port))

        self.protocol = PatchProtocol(
            self.uuid, self.patch_port, self.update_patch_state
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            loop.create_datagram_endpoint(lambda: self.protocol, sock=self.sock)
        )

    def add_input(self, data_callback, **kwargs) -> InputJack:
        # Adds a new input to the module
        jack = InputJack(
            self, data_callback, id=len(self.outputs) + len(self.inputs), **kwargs
        )
        self.inputs.append(jack)
        return jack

    def add_output(self, **kwargs) -> OutputJack:
        # Adds a new output to the module
        jack = OutputJack(self, id=len(self.outputs) + len(self.inputs), **kwargs)
        self.outputs.append(jack)
        return jack

    def update_patch(self):
        # Trigger in update in the shared state
        self.protocol.update(
            [j.state for j in chain(self.inputs, self.outputs) if j.state]
        )

    def update_patch_state(self, patch_state):
        if self.patch_state != patch_state:
            self.patch_state = patch_state
            print(patch_state)


class PatchState(Enum):
    # Global state possibilities
    IDLE = 0  # No buttons pushed across all modules
    PATCH_ENABLED = 1  # One single button pushed
    PATCH_TOGGLED = 2  # Two buttons pushed, consisting of an input and output
    BLOCKED = 3  # Three or more buttons pushed or two of the same type


class PatchProtocol(asyncio.DatagramProtocol):

    states = {}
    broadcast_addrs = []

    def __init__(self, uuid, port, state_callback) -> None:
        self.uuid = uuid
        self.port = port
        self.state_callback = state_callback

        self.states[uuid] = []

        for interface in netifaces.interfaces():
            interfaces_details = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in interfaces_details:
                for detail in interfaces_details[netifaces.AF_INET]:
                    if detail["addr"] != "127.0.0.1":
                        self.broadcast_addrs.append((detail["broadcast"], port))

        super().__init__()

    def connection_made(self, transport):
        print("Connection made")
        self.transport = transport

    def datagram_send(self, json_msg):
        print("=>")
        print(json_msg)
        payload = bytes(json.dumps(json_msg), "utf8")
        for addr in self.broadcast_addrs:
            self.transport.sendto(payload, addr)
            print(addr)

    def update(self, local_state):
        # Updates the local state and triggers a global check-in
        self.states[self.uuid] = local_state
        self.datagram_send(
            {"message": "UPDATE", "uuid": self.uuid, "state": local_state}
        )
        self.push_update()

    def push_update(self):
        self.state_callback(
            PatchState(min(3, sum(len(v) for k, v in self.states.items())))
        )

    def datagram_received(self, data: bytes, addr) -> None:
        try:
            response = json.loads(data)
        except json.JSONDecodeError:
            return
        if any(k not in response for k in ("message", "uuid", "state")):
            return
        if response["uuid"] == self.uuid:
            return

        if response["message"] == "UPDATE":
            self.states[response["uuid"]] = response["state"]
            self.push_update()
