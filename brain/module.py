import itertools
import logging
import netifaces
import numpy as np
import uuid

from collections import deque
from typing import Dict, Final, Set, Tuple

from .interfaces import (
    EventHandler,
    GlobalState,
    HeldInputJack,
    HeldOutputJack,
    LocalState,
    ModuleUuid,
    PatchState,
)
from .parsers import Message, MessageType
from .servers import InputJackListener, OutputJackServer, PatchServer


class Jack:
    patch_enabled = False
    patch_member = False
    _id_iter = itertools.count()

    def __init__(self, name: str):
        self.name: Final = name
        self.id: Final = str(next(Jack._id_iter))

    def is_patched(self) -> bool:
        raise NotImplementedError

    def get_color(self) -> int:
        raise NotImplementedError


class InputJack(Jack):
    """An input jack which receives data from an output jack over the network. This is not
    typically instantiated directly but rather through ``Module.add_input``.

    :param parent_module: Reference to the owning ``Module``

    :param name: Identifier describing the input jack

    :param data_callback: Function that is called when new data arrives at the input jack. This
        callback fires immediately when the data is received, so use ``process_callback`` if a
        synchronized consumption of multiple inputs is desired (i.e. the signals are not processed
        independently).
    """

    def __init__(self, parent_module, name: str, data_callback):
        self.parent_module = parent_module
        self.callback = data_callback
        self.data_queue = deque()
        self.last_seen_data = np.zeros(
            (Module.block_size, Module.channels), dtype=Module.sample_type
        )
        self.connected_jack = None
        self.jack_listener = InputJackListener(self.proto_callback)

        super().__init__(name)

    def is_patched(self) -> bool:
        """Check if input jack is currently connected to a patch

        :return: ``True`` if connected
        """
        return self.connected_jack is not None

    def clear(self):
        if self.is_patched():
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

        self.jack_listener.connect(address, port)

    def update(self):
        self.jack_listener.update()

    def proto_callback(self, data):
        if self.callback is not None:
            self.callback(data)
        data = np.frombuffer(data, dtype=Module.sample_type)
        data = data.reshape((len(data) // Module.channels, Module.channels))
        self.last_seen_data = data.copy()
        self.data_queue.appendleft(data)
        self.parent_module._check_process()

    def get_data(self) -> np.ndarray:
        """Pull pending data from the jack. In the event that data is not available, this will
        return a copy of the last seen packet. Used in response to a ``process_callback``.

        :return: An array of shape (X, ``Module.channels``) of data type ``Module.sample_type``,
            where X is the number of samples sent in a packet window"""
        if len(self.data_queue) > 0:
            return self.data_queue.pop()
        else:
            return self.last_seen_data.copy()

    def get_color(self) -> int:
        if not self.is_patched():
            return 330
        else:
            return self.color


class OutputJack(Jack):
    """An output jack which sends data to input jacks over the network. This is not
    typically instantiated directly but rather through ``Module.add_output``.

    :param address: ip4 address to sink data

    :param name: Identifier describing the output jack

    :param color: An HSV Hue value for the jack's primary color in [0, 360). This color is
        propagated to any input jacks that it is patched to.
    """

    def __init__(self, address: str, name: str, color: int):
        self.color = color
        self.connected_jacks: Set[Tuple[str, str]] = set()
        self.jack_server = OutputJackServer(address)
        self.endpoint = self.jack_server.endpoint

        super().__init__(name)

    def send(self, data: bytes) -> None:
        """Send data out through this jack. Caller is responsible for maintaining packet timing.
        Currently, this sends data out to the network at all times.

        :data: Data to be sent in raw bytes
        """
        self.jack_server.datagram_send(data)

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
        """Check if output jack is currently connected to a patch

        :return: ``True`` if connected
        """
        return len(self.connected_jacks) > 0

    def clear(self):
        self.connected_jacks.clear()

    def get_color(self) -> int:
        return self.color


class Module:
    """The ``Module`` object mediates all of the patching and dataflow between all other modules on
    the network. Typically, a module only needs to be written as a processor on the input state to
    the output state and handle the associated user interface. Ideally, most of this would be placed
    on the python module level rather than the class level, but it is included here in order to
    maintain parity with the C++/static implementation.

    :param name: The name of the module

    :param event_handler: Instance of an ``EventHandler`` used to process application events. The
        application should either create its own class that inherits from ``EventHandler`` or create
        a new instance and modify the class methods.
    """

    #: Preferred communication subnet in case multiple network interfaces are present
    preferred_broadcast: Final = "10.255.255.255"

    #: Port used to establish the global state and create new patch connections
    patch_port: Final = 19874

    #: Frequency in packets per second to send audio and CV data
    packet_rate: Final = 1000

    #: Audio sample rate in Hz (must be a multiple of ``packet_rate``)
    sample_rate: Final = 48000

    #: Number of samples in a full-length packet (``sample_rate`` / ``packet_rate``)
    block_size: Final = 48

    #: Number of independent audio processing channels
    channels: Final = 8

    #: Maximum number of states to buffer
    buffer_size: Final = 100

    #: Sample data type
    sample_type: Final = np.int16

    def __init__(self, name: str, event_handler: EventHandler = None):
        self.name = name
        self.event_handler = event_handler or EventHandler()
        self.uuid: ModuleUuid = str(uuid.uuid4())
        self.global_state = GlobalState(PatchState.IDLE, {}, {})

        self.inputs: Dict[str, InputJack] = {}
        self.outputs: Dict[str, OutputJack] = {}
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

        self.patch_server = PatchServer(
            self.uuid,
            self.broadcast_addr,
            self.patch_port,
            self.event_callback,
        )

    def update(self):
        """Process all pending tasks: send and recieve directives, audio and control data and
        perform callbacks if requested. This should be run periodically in an event loop or a
        thread.
        """
        self.patch_server.update()
        for jack in self.inputs.values():
            jack.update()

    def add_input(self, name: str, data_callback=None) -> InputJack:
        """Adds a new input jack to the module

        :param name: Identifier describing the new jack

        :param data_callback: Function that is called when new data arrives at the input jack. This
            callback fires immediately when the data is received, so use ``process_callback`` if a
            synchronized consumption of multiple inputs is desired (i.e. the signals are not
            processed independently).

        :return: The created jack instance
        """
        jack = InputJack(self, name, data_callback)
        self.inputs[jack.id] = jack
        return jack

    def add_output(self, name: str, color: int) -> OutputJack:
        """Adds a new output jack to the module

        :param name: Identifier describing the new jack

        :param color: An HSV Hue value for the jack's primary color in [0, 360). This color is
            propagated to any input jacks that it is patched to.

        :return: The created jack instance
        """
        jack = OutputJack(self.broadcast_addr["broadcast"], name, color)
        self.outputs[jack.id] = jack
        return jack

    def get_jack_color(self, jack: Jack) -> int:
        """Returns the assigned HSV hue of the jack"""
        return jack.get_color()

    def get_patch_state(self) -> PatchState:
        """Retrieves the global patch state"""
        return self.global_state.patch_state

    def is_input(self, jack: Jack) -> bool:
        """Check if given jack is an input jack"""
        return isinstance(jack, InputJack)

    def is_patched(self, jack: Jack) -> bool:
        """Check if a jack is currently connected to a patch

        :param jack: Input or output jack to check

        :return: ``True`` if connected
        """
        return jack.is_patched()

    def is_patch_member(self, jack: Jack) -> bool:
        """During ``PatchState.PATCH_ENABLED``, returns whether a jack is currently patched to the
        held input or output jack.
        """
        return jack.patch_member

    def get_data(self, jack: InputJack) -> np.ndarray:
        """Pull pending data from the jack. In the event that data is not available, this will
        return a copy of the last seen packet. Used in response to a ``process_callback``.

        :param jack: Input jack to receive data from

        :return: An array of shape (X, ``Module.channels``) of data type ``Module.sample_type``,
            where X is the number of samples sent in a packet window"""
        return jack.get_data()

    def send_data(self, jack: OutputJack, data: np.ndarray) -> None:
        """Send data through an output jack. Caller is responsible for maintaining packet timing.
        Currently, this sends data out to the network at all times.

        :param jack: Output jack through which to send

        :param data: An array of shape (X, ``Module.channels``) of data type ``Module.sample_type``,
            where X is the number of samples sent in a packet window
        """
        jack.send(data.tobytes())

    def set_patch_enabled(self, jack: Jack, state: bool) -> None:
        """Indicate the jack is available for patching (for instance, the patch button is held down)
        and notify other modules

        :param jack: Input or output jack to set the state

        :param state: Value to set
        """
        if jack.patch_enabled != state:
            jack.patch_enabled = state
            self.update_patch()

    def update_patch(self) -> None:
        """Triggers an update in the shared global state"""
        held_inputs = [
            HeldInputJack(self.uuid, jack.id)
            for jack in self.inputs.values()
            if jack.patch_enabled
        ]
        held_outputs = [
            HeldOutputJack(self.uuid, jack.id, jack.color, jack.endpoint[1])
            for jack in self.outputs.values()
            if jack.patch_enabled
        ]
        self.patch_server.message_send(
            Message(
                self.uuid, MessageType.UPDATE, LocalState(held_inputs, held_outputs)
            )
        )
        self.global_state.held_inputs[self.uuid] = held_inputs
        self.global_state.held_outputs[self.uuid] = held_outputs
        self.update_patch_state()

    def halt_callback(self) -> None:
        self.event_handler.halt()

    def halt_all(self) -> None:
        """Sends a halt directive to all connected modules"""
        self.patch_server.message_send(Message("GLOBAL", MessageType.HALT))

    def update_patch_state(self):
        """Callback used to manages changes in the global state"""
        active_inputs = list(itertools.chain(*self.global_state.held_inputs.values()))
        active_outputs = list(itertools.chain(*self.global_state.held_outputs.values()))
        total_inputs = len(active_inputs)
        total_outputs = len(active_outputs)

        if total_inputs >= 2 or total_outputs >= 2:
            patch_state = PatchState.BLOCKED
        elif total_inputs == 1 and total_outputs == 1:
            patch_state = PatchState.PATCH_TOGGLED
        elif total_inputs == 1 or total_outputs == 1:
            patch_state = PatchState.PATCH_ENABLED
        else:
            patch_state = PatchState.IDLE

        if self.global_state.patch_state != patch_state:
            self.global_state.patch_state = patch_state
            logging.info("global_state: " + str(self.global_state))

            for jack in self.inputs.values():
                jack.patch_member = False
            for jack in self.outputs.values():
                jack.patch_member = False

            if patch_state == PatchState.PATCH_ENABLED:
                if total_inputs == 1:
                    held_input_uuid = active_inputs[0].uuid
                    held_input_id = active_inputs[0].id
                    if self.uuid == held_input_uuid:
                        self.inputs[held_input_id].patch_member = True
                    for jack in self.outputs.values():
                        jack.patch_member = jack.is_connected(
                            held_input_uuid, held_input_id
                        )
                elif total_outputs == 1:
                    held_output_uuid = active_outputs[0].uuid
                    held_output_id = active_outputs[0].id
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
                    if output.uuid == self.uuid and output.id == output_jack.id:
                        continue
                    if output_jack.is_connected(input.uuid, input.id):
                        output_jack.disconnect(input.uuid, input.id)

                if input.uuid == self.uuid:
                    self.toggle_input_connection(input, output)
                if output.uuid == self.uuid:
                    self.toggle_output_connection(input, output)

            self.event_handler.patch(patch_state)

    def toggle_input_connection(self, input, output) -> None:
        """Toggles an input connection that is owned by this module, either connecting it to the
        given output or disconnecting it if it is already connected. This operation only updates the
        local state of the input jack, rather than triggering an update across all modules.

        :param input: The input jack to be toggled

        :param output: The external output jack to connect to or disconnect from
        """
        input_jack = self.inputs[input.id]
        output_uuid, output_id = output.uuid, output.id
        if input_jack.is_connected(output_uuid, output_id):
            input_jack.disconnect(output_uuid, output_id)
        else:
            input_jack.connect(
                self.broadcast_addr["addr"],
                output.port,
                output.color,
                output.uuid,
                output.id,
            )

    def toggle_output_connection(self, input, output) -> None:
        """Toggles an output connection that is owned by this module, either connecting it to the
        given input or disconnecting it if it is already connected. This operation only updates the
        local state of the output jack, rather than triggering an update across all modules.

        :param input: The external input back to connect to or disconnect from

        :param output: The output jack to be toggled
        """
        output_jack = self.outputs[output.id]
        input_uuid, input_id = input.uuid, input.id
        if output_jack.is_connected(input_uuid, input_id):
            output_jack.disconnect(input_uuid, input_id)
        else:
            output_jack.connect(input_uuid, input_id)

    def _check_process(self) -> None:
        """Callback that determines if data is ready for a synchronized processing step across all of
        the owned input jacks
        """

        data_available = True
        for jack in self.inputs.values():
            if not jack.is_patched():
                continue
            if len(jack.data_queue) >= self.buffer_size:
                self.event_handler.process()
                return
            if len(jack.data_queue) == 0:
                data_available = False
        if data_available:
            self.event_handler.process()

    def event_callback(self, message: Message):
        if message.type == MessageType.HALT:
            self.halt_callback()
        if message.type == MessageType.UPDATE:
            if message.local_state is not None:
                self.global_state.held_inputs[
                    message.uuid
                ] = message.local_state.held_inputs
                self.global_state.held_outputs[
                    message.uuid
                ] = message.local_state.held_outputs

                self.update_patch_state()
