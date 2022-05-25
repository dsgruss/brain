import asyncio
import itertools
import json
import logging
import netifaces
import numpy as np
import random
import socket
import uuid

from collections import deque
from enum import Enum


class Jack:
    patch_enabled = False
    id_iter = itertools.count()

    def __init__(self, parent_module, name):
        self.parent_module = parent_module
        self.name = name
        self.id = str(next(Jack.id_iter))

    def set_patch_enabled(self, state: bool):
        # Indicate the jack is available for patching and notify other modules
        if self.patch_enabled != state:
            self.patch_enabled = state
            self.parent_module.update_patch()


class InputJack(Jack):
    def __init__(self, parent_module, data_callback, name):
        self.callback = data_callback
        self.data_queue = deque()
        self.last_seen_data = np.zeros(
            (Module.block_size, Module.channels), dtype=Module.sample_type
        )
        self.connected_jack = None

        super().__init__(parent_module, name)

    def is_patched(self) -> bool:
        return self.connected_jack is not None

    def clear(self):
        if self.is_patched():
            self.endpoint.close()
            self.sock.close()
            self.connected_jack = None

    def disconnect(self, output_uuid, output_id):
        if self.is_connected(output_uuid, output_id):
            self.clear()

    def is_connected(self, output_uuid, output_id):
        logging.info("Connected input jack test:")
        logging.info(self.connected_jack)
        logging.info(((output_uuid, output_id)))
        return self.connected_jack == (output_uuid, output_id)

    def connect(self, address, port, output_color, output_uuid, output_id):
        if self.is_patched():
            self.clear()
        self.color = output_color
        self.connected_jack = (output_uuid, output_id)

        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
        self.sock.bind((address, port))

        self.protocol = DataProtocol(self)
        loop = asyncio.get_event_loop()
        self.endpoint = loop.create_datagram_endpoint(
            lambda: self.protocol, sock=self.sock
        )
        loop.create_task(self.endpoint)

    def proto_callback(self, data):
        if self.callback is not None:
            self.callback(data)
        data = np.frombuffer(data, dtype=Module.sample_type)
        data = data.reshape((len(data) // Module.channels, Module.channels))
        self.last_seen_data = data.copy()
        self.data_queue.appendleft(data)
        self.parent_module.check_process()

    def get_data(self):
        if len(self.data_queue) > 0:
            return self.data_queue.pop()
        else:
            return self.last_seen_data.copy()


class OutputJack(Jack):
    def __init__(self, parent_module, address, name, color):
        self.color = color
        self.connected_jacks = set()
        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

        # For now we just pick a port, but this should be negotiated during device discovery
        self.endpoint = (address, random.randrange(49152, 65535))
        logging.info("Jack endpoint: " + str(self.endpoint))

        super().__init__(parent_module, name)

    def send(self, data: bytes):
        # Currently sending all the data at all times
        self.sock.sendto(data, self.endpoint)

    def connect(self, input_uuid, input_id):
        self.connected_jacks.add((input_uuid, input_id))

    def is_connected(self, input_uuid, input_id):
        logging.info("Connected output jack test:")
        logging.info(self.connected_jacks)
        logging.info(((input_uuid, input_id)))
        return (input_uuid, input_id) in self.connected_jacks

    def disconnect(self, input_uuid, input_id):
        self.connected_jacks.discard((input_uuid, input_id))

    def is_patched(self) -> bool:
        return len(self.connected_jacks) > 0

    def clear(self):
        self.connected_jacks.clear()


class PatchState(Enum):
    """Global state possibilities"""

    IDLE = 0  # No buttons pushed across all modules
    PATCH_ENABLED = 1  # One single button pushed
    PATCH_TOGGLED = 2  # Two buttons pushed, consisting of an input and output
    BLOCKED = 3  # Three or more buttons pushed or two of the same type


class Module:
    """The `Module` object mediates all of the patching and dataflow between all other modules on
    the network. Typically, a module only needs to be written as a processor on the input state
    to the output state and handle the associated user interface.

    :param name: the name of the module

    :param patching_callback: function called when the global patch state changes

    :param process_callback: function called for the syncronized processing step

    :param abort_callback: function called for a global shutdown event
    """

    # Preferred communication subnet in case multiple network interfaces are present
    preferred_broadcast = "10.255.255.255"

    # Port used to establish the global state and create new patch connections
    patch_port = 19874

    # Frequency in packets per second to send audio and CV data
    packet_rate = 1000

    # Audio sample rate in Hz (must be a multiple of packet_rate)
    sample_rate = 48000

    # Number of samples in a full-length packet (sample_rate / packet_rate)
    block_size = 48

    # Number of independent audio processing channels
    channels = 8

    # Maximum number of states to buffer
    buffer_size = 100

    # Sample data type
    sample_type = np.int16

    def __init__(
        self,
        name: str,
        patching_callback=None,
        process_callback=None,
        abort_callback=None,
    ):
        self.name = name
        self.patching_callback = patching_callback
        self.process_callback = process_callback
        self.uuid = str(uuid.uuid4())
        self.patch_state = PatchState.IDLE

        self.inputs = {}
        self.outputs = {}
        self.broadcast_addr = None

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
            abort_callback,
        )

    def start(self):
        if self.patching_callback is not None:
            self.patching_callback(self.patch_state)

        loop = asyncio.get_event_loop()
        loop.create_task(
            loop.create_datagram_endpoint(lambda: self.protocol, sock=self.sock)
        )

    def add_input(self, name, data_callback=None) -> InputJack:
        # Adds a new input to the module
        jack = InputJack(self, data_callback, name)
        self.inputs[jack.id] = jack
        return jack

    def add_output(self, name, color) -> OutputJack:
        # Adds a new output to the module
        jack = OutputJack(self, self.broadcast_addr["broadcast"], name, color)
        self.outputs[jack.id] = jack
        return jack

    def update_patch(self):
        # Trigger in update in the shared state
        s = {
            "inputs": [
                {"id": jack.id, "type": "input"}
                for jack in self.inputs.values()
                if jack.patch_enabled
            ],
            "outputs": [
                {
                    "id": jack.id,
                    "type": "output",
                    "address": jack.endpoint[0],
                    "port": jack.endpoint[1],
                    "color": jack.color,
                }
                for jack in self.outputs.values()
                if jack.patch_enabled
            ],
        }
        self.protocol.update(s)

    def abort_all(self):
        self.protocol.abort_all()

    def update_patch_state(self, patch_state, active_inputs, active_outputs):
        if self.patch_state != patch_state:
            self.patch_state = patch_state
            logging.info(patch_state)

            for jack in self.inputs.values():
                jack.patch_member = False
            for jack in self.outputs.values():
                jack.patch_member = False

            if patch_state == PatchState.PATCH_ENABLED:
                if len(active_inputs) == 1:
                    held_input_uuid = active_inputs[0]["uuid"]
                    held_input_id = active_inputs[0]["id"]
                    if self.uuid == held_input_uuid:
                        self.inputs[held_input_id].patch_member = True
                    for jack in self.outputs.values():
                        jack.patch_member = jack.is_connected(
                            held_input_uuid, held_input_id
                        )
                elif len(active_outputs) == 1:
                    held_output_uuid = active_outputs[0]["uuid"]
                    held_output_id = active_outputs[0]["id"]
                    if self.uuid == held_output_uuid:
                        self.outputs[held_output_id].patch_member = True
                    for jack in self.inputs.values():
                        jack.patch_member = jack.is_connected(
                            held_output_uuid, held_output_id
                        )

            if patch_state == PatchState.PATCH_TOGGLED:
                input = active_inputs[0]
                output = active_outputs[0]
                for output_jack in self.outputs.values():
                    if output["uuid"] == self.uuid and output["id"] == output_jack.id:
                        continue
                    if output_jack.is_connected(input["uuid"], input["id"]):
                        output_jack.disconnect(input["uuid"], input["id"])

                if input["uuid"] == self.uuid:
                    self.toggle_input_connection(input, output)
                if output["uuid"] == self.uuid:
                    self.toggle_output_connection(input, output)

            if self.patching_callback is not None:
                self.patching_callback(patch_state)

    def toggle_input_connection(self, input, output):
        input_jack = self.inputs[input["id"]]
        output_uuid, output_id = output["uuid"], output["id"]
        if input_jack.is_connected(output_uuid, output_id):
            input_jack.disconnect(output_uuid, output_id)
        else:
            input_jack.connect(
                self.broadcast_addr["addr"],
                output["port"],
                output["color"],
                output["uuid"],
                output["id"],
            )

    def toggle_output_connection(self, input, output):
        output_jack = self.outputs[output["id"]]
        input_uuid, input_id = input["uuid"], input["id"]
        if output_jack.is_connected(input_uuid, input_id):
            output_jack.disconnect(input_uuid, input_id)
        else:
            output_jack.connect(input_uuid, input_id)

    def check_process(self):
        if self.process_callback is None:
            return

        data_available = True
        for jack in self.inputs.values():
            if not jack.is_patched():
                continue
            if len(jack.data_queue) >= self.buffer_size:
                self.process_callback()
                return
            if len(jack.data_queue) == 0:
                data_available = False
        if data_available:
            self.process_callback()


class DataProtocol(asyncio.DatagramProtocol):
    def __init__(self, jack) -> None:
        self.jack = jack

        super().__init__()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        self.jack.proto_callback(data)


class PatchProtocol(asyncio.DatagramProtocol):
    def __init__(
        self, uuid, broadcast_addr, port, state_callback, abort_callback
    ) -> None:
        self.uuid = uuid
        self.broadcast_addr = broadcast_addr
        self.port = port
        self.state_callback = state_callback
        self.abort_callback = abort_callback

        self.states = {uuid: {"inputs": [], "outputs": []}}

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

    def abort_all(self):
        self.datagram_send({"message": "ABORT", "uuid": "GLOBAL"})

    def push_update(self):
        active_inputs = []
        active_outputs = []
        for uuid, full_state in self.states.items():
            for state in full_state["inputs"]:
                a = state.copy()
                a["uuid"] = uuid
                active_inputs.append(a)
            for state in full_state["outputs"]:
                a = state.copy()
                a["uuid"] = uuid
                active_outputs.append(a)
        logging.info("Global state: " + str(active_inputs) + " " + str(active_outputs))

        if len(active_inputs) >= 2 or len(active_outputs) >= 2:
            patch_state = PatchState.BLOCKED
        elif len(active_inputs) == 1 and len(active_outputs) == 1:
            patch_state = PatchState.PATCH_TOGGLED
        elif len(active_inputs) + len(active_outputs) == 1:
            patch_state = PatchState.PATCH_ENABLED
        else:
            patch_state = PatchState.IDLE
        self.state_callback(patch_state, active_inputs, active_outputs)

    def datagram_received(self, data: bytes, addr) -> None:
        try:
            response = json.loads(data)
        except json.JSONDecodeError:
            return
        if any(k not in response for k in ("message", "uuid")):
            return
        if response["uuid"] == self.uuid:
            return

        logging.info("<= " + str(response))
        if response["message"] == "UPDATE":
            self.states[response["uuid"]] = response["state"]
            self.push_update()
        if response["message"] == "ABORT":
            if self.abort_callback is not None:
                self.abort_callback()
