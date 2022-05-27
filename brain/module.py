import itertools
import logging
import netifaces
import numpy as np
import uuid

from typing import Dict

from .constants import BUFFER_SIZE, PREFERRED_BROADCAST
from .interfaces import (
    EventHandler,
    GlobalState,
    HeldInputJack,
    HeldOutputJack,
    LocalState,
    ModuleUuid,
    PatchState,
)
from .jacks import Jack, InputJack, OutputJack
from .parsers import Message, MessageType
from .servers import PatchServer


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
            if detail["broadcast"] == PREFERRED_BROADCAST:
                self.broadcast_addr = detail

        self.patch_server = PatchServer(
            self.uuid, self.broadcast_addr["addr"], self.broadcast_addr["broadcast"]
        )

    def update(self):
        """Process all pending tasks: send and recieve directives, audio and control data and
        perform callbacks if requested. This should be run periodically in an event loop or a
        thread.
        """
        while (message := self.patch_server.get_message()) is not None:
            self.event_process(message)
        for jack in self.inputs.values():
            while jack.update():
                self.check_process()

    def add_input(self, name: str) -> InputJack:
        """Adds a new input jack to the module

        :param name: Identifier describing the new jack

        :return: The created jack instance
        """
        jack = InputJack(name)
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
        return a copy of the last seen packet. Used in response to a ``process`` callback.

        :param jack: Input jack to receive data from

        :return: An array of shape (X, ``brain.CHANNELS``) of data type ``brain.SAMPLE_TYPE``,
            where X is the number of samples sent in a packet window"""
        return jack.get_data()

    def send_data(self, jack: OutputJack, data: np.ndarray) -> None:
        """Send data through an output jack. Caller is responsible for maintaining packet timing.
        Currently, this sends data out to the network at all times.

        :param jack: Output jack through which to send

        :param data: An array of shape (X, ``brain.CHANNELS``) of data type ``brain.SAMPLE_TYPE``,
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
        """Manages changes in the global state"""
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

    def check_process(self) -> None:
        """Determine if data is ready for a synchronized processing step"""

        data_available = True
        for jack in self.inputs.values():
            if not jack.is_patched():
                continue
            if len(jack.data_queue) >= BUFFER_SIZE:
                self.event_handler.process()
                return
            if len(jack.data_queue) == 0:
                data_available = False
        if data_available:
            self.event_handler.process()

    def event_process(self, message: Message):
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
