import asyncio
import netifaces
import json
import logging
import random
import socket
import uuid

from enum import Enum


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

        self.patched = False

        super().__init__(parent_module)

    def is_patched(self) -> bool:
        return self.patched

    def clear(self):
        if self.is_patched():
            self.endpoint.close()
            self.sock.close()
            self.patched = False

    def connect(self, address, port, sample_rate):
        self.sending_sample_rate = sample_rate

        if self.is_patched():
            self.clear()

        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
        self.sock.bind((address, port))

        self.protocol = DataProtocol(self)
        loop = asyncio.get_event_loop()
        self.endpoint = loop.create_datagram_endpoint(
            lambda: self.protocol, sock=self.sock
        )
        loop.create_task(self.endpoint)

        self.patched = True

    def proto_callback(self, data):
        self.callback(data, self.sending_sample_rate)


class OutputJack(Jack):
    def __init__(self, parent_module, address, **kwargs):
        self.params = kwargs

        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        # For now we just pick a port, but this should be negotiated during device discovery
        self.endpoint = (address, random.randrange(49152, 65535))
        logging.info("Jack endpoint: " + str(self.endpoint))

        super().__init__(parent_module)

    def send(self, data: bytes):
        # Currently sending all the data at all times
        self.sock.sendto(data, self.endpoint)


class Module:
    # Class to handle networking and discovery layers for each module
    inputs = []
    outputs = []
    patch_port = 19874
    preferred_broadcast = "10.255.255.255"
    broadcast_addr = None

    def __init__(self, name, patching_callback=None):
        # Initializes the module and allows for discovery by management requests
        self.name = name
        self.patching_callback = patching_callback
        self.uuid = str(uuid.uuid4())
        self.patch_state = PatchState.IDLE
        if patching_callback is not None:
            patching_callback(self.patch_state)

        addresses = []
        for interface in netifaces.interfaces():
            interfaces_details = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in interfaces_details:
                for detail in interfaces_details[netifaces.AF_INET]:
                    addresses.append(detail)

        logging.info("Addresses found: " + str(addresses))
        if len(addresses) == 0:
            return

        self.broadcast_addr = addresses[0]
        for detail in addresses:
            if detail["broadcast"] == self.preferred_broadcast:
                self.broadcast_addr = detail

        # The socket is created manually here because the handler doesn't appear to appear to allow
        # an address reuse, even though we are using a broadcast

        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
        self.sock.bind((self.broadcast_addr["addr"], self.patch_port))

        self.protocol = PatchProtocol(
            self.uuid,
            self.broadcast_addr["broadcast"],
            self.patch_port,
            self.update_patch_state,
        )
        loop = asyncio.get_event_loop()
        loop.create_task(
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
        jack = OutputJack(
            self,
            self.broadcast_addr["broadcast"],
            id=len(self.outputs) + len(self.inputs),
            **kwargs
        )
        self.outputs.append(jack)
        return jack

    def update_patch(self):
        # Trigger in update in the shared state
        s = [{"id": j.params["id"], "type": "input"} for j in self.inputs if j.state]
        s += [
            {
                "id": j.params["id"],
                "type": "output",
                "address": j.endpoint[0],
                "port": j.endpoint[1],
                "sample_rate": j.params["sample_rate"],
            }
            for j in self.outputs
            if j.state
        ]
        self.protocol.update(s)

    def update_patch_state(self, patch_state, global_states):
        if self.patch_state != patch_state:
            self.patch_state = patch_state
            if self.patching_callback is not None:
                self.patching_callback(patch_state)
            logging.info(patch_state)

            if patch_state == PatchState.PATCH_TOGGLED:
                if global_states[0]["type"] == "input":
                    input = global_states[0]
                    output = global_states[1]
                else:
                    input = global_states[1]
                    output = global_states[0]
                if input["uuid"] == self.uuid:
                    self.make_connection(input, output)

    def make_connection(self, input, output):
        input_jack = [j for j in self.inputs if j.params["id"] == input["id"]][0]
        input_jack.connect(
            self.broadcast_addr["addr"], output["port"], output["sample_rate"]
        )


class PatchState(Enum):
    # Global state possibilities
    IDLE = 0  # No buttons pushed across all modules
    PATCH_ENABLED = 1  # One single button pushed
    PATCH_TOGGLED = 2  # Two buttons pushed, consisting of an input and output
    BLOCKED = 3  # Three or more buttons pushed or two of the same type


class DataProtocol(asyncio.DatagramProtocol):
    def __init__(self, jack) -> None:
        self.jack = jack

        super().__init__()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        self.jack.proto_callback(data)


class PatchProtocol(asyncio.DatagramProtocol):

    states = {}

    def __init__(self, uuid, broadcast_addr, port, state_callback) -> None:
        self.uuid = uuid
        self.broadcast_addr = broadcast_addr
        self.port = port
        self.state_callback = state_callback

        self.states[uuid] = []

        super().__init__()

    def connection_made(self, transport):
        logging.info("Patching broadcast connection made")
        self.transport = transport

    def datagram_send(self, json_msg):
        logging.info(
            "=> " + str((self.broadcast_addr, self.port)) + ": " + str(json_msg)
        )
        payload = bytes(json.dumps(json_msg), "utf8")
        self.transport.sendto(payload, (self.broadcast_addr, self.port))

    def update(self, local_state):
        # Updates the local state and triggers a global check-in
        self.states[self.uuid] = local_state
        self.datagram_send(
            {"message": "UPDATE", "uuid": self.uuid, "state": local_state}
        )
        self.push_update()

    def push_update(self):
        all_states = []
        for uuid, state_list in self.states.items():
            for state in state_list:
                a = state.copy()
                a["uuid"] = uuid
                all_states.append(a)
        logging.info(all_states)
        if len(all_states) >= 3:
            self.state_callback(PatchState.BLOCKED, all_states)
        elif len(all_states) == 2:
            if all_states[0]["type"] == all_states[1]["type"]:
                self.state_callback(PatchState.BLOCKED, all_states)
            else:
                self.state_callback(PatchState.PATCH_TOGGLED, all_states)
        elif len(all_states) == 1:
            self.state_callback(PatchState.PATCH_ENABLED, all_states)
        else:
            self.state_callback(PatchState.IDLE, all_states)

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
