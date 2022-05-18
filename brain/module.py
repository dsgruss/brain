import netifaces
import json
import socket
import threading
import time
import uuid

from itertools import chain
from struct import unpack

from brain import consensus

class InputJack:
    def __init__(self, data_callback, params):
        self.callback = data_callback
        self.params = params
        self.state = False

    def patch_enabled(self, state: bool):
        # Indicate the jack is available for patching and notify other modules
        if self.state != state:
            self.state = state
            self._owning_module.update_patch()


    def is_patched(self) -> bool:
        # Returns True if another module is sending data to the jack
        return False

    def clear(self):
        # Disconnect this jack from all other modules
        pass


class OutputJack:
    def __init__(self, **kwargs):
        self.params = kwargs
        self.destinations = []
        self.state = False

    def send(self, data: bytes):
        rtp_header = bytes("############", "ASCII")
        for loc in self.destinations:
            self._owning_module._sock.sendto(rtp_header + data, loc)

    def patch_enabled(self, state: bool):
        # Indicate the jack is available for patching and notify other modules
        if self.state != state:
            self.state = state
            self._owning_module.update_patch()

    def is_patched(self) -> bool:
        # Returns True if another module is consuming the data from this jack
        return False

    def clear(self):
        # Disconnect this jack from all other modules
        pass


class Module:
    # Class to handle networking and discovery layers for each module
    inputs = []
    outputs = []

    _network_interfaces = []
    _sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

    directive_port = 12345

    def __init__(self, name, patching_callback=None):
        # Initializes the module and allows for discovery by management requests
        self.name = name
        self.patching_callback = patching_callback
        self._uuid = uuid.uuid4()

        print("Discovering network interfaces...")

        for interface in netifaces.interfaces():
            interfaces_details = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in interfaces_details:
                self._network_interfaces.extend(interfaces_details[netifaces.AF_INET])

        print(self._network_interfaces)
        for interface in self._network_interfaces:
            threading.Thread(
                target=self._loop, args=(interface["addr"],), daemon=True
            ).start()

        self._consensus = consensus.Consensus(None, self._uuid)


    def _loop(self, local_address):
        # Thread that responds to identification and control commands

        sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)

        for _ in range(10):
            try:
                sock.bind((local_address, self.directive_port))
                break
            except OSError:
                self.directive_port += 1
                continue
        else:
            print("Unable to find open port.")
            exit(-1)

        env = {"name": self.name, "id": self._uuid, "inputs": [], "outputs": []}

        print(f"Listening for directives on {local_address}:{self.directive_port}...")

        while True:
            msg, addr = sock.recvfrom(1500)
            if msg.startswith(b"IDENTIFY"):
                print("Identification command received.")
                env.outputs = [o.params for o in self.outputs]
                sock.sendto(bytes(json.dumps(env), "utf8"), addr)
            elif msg.startswith(b"REQUEST"):
                print("Patch mapping command received.")
                directive, destination_address, destination_port, id = unpack(
                    "!10s4shB", msg
                )
                address = (socket.inet_ntoa(destination_address), destination_port)
                for o in self.outputs:
                    if o.params.id == id:
                        o.destinations.append(address)
            elif msg.startswith(b"RESET"):
                print("Reset command received.")
                for o in self.outputs:
                    o.destinations.clear()

    def add_input(self, data_callback) -> InputJack:
        # Adds a new input to the module
        jack = InputJack(data_callback)
        jack._owning_module = self
        self.inputs.append(jack)
        return jack

    def add_output(self, **kwargs) -> OutputJack:
        # Adds a new output to the module
        jack = OutputJack(id=len(self.outputs), **kwargs)
        jack._owning_module = self
        self.outputs.append(jack)
        return jack

    def update_patch(self):
        # Trigger in update in the shared state
        self._consensus.update([j.state for j in chain(self.inputs, self.outputs) if j.state])
