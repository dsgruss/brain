import logging
import netifaces
import numpy as np
import time
import uuid

from typing import Dict, List
from collections import defaultdict

from brain.leader_election import LeaderElection

from .constants import (
    BLOCK_SIZE,
    CHANNELS,
    PACKET_RATE,
    PREFERRED_BROADCAST,
    SAMPLE_TYPE,
)
from .interfaces import (
    EventHandler,
    PatchState,
)
from .jacks import Jack, InputJack, OutputJack
from .servers import PatchServer
from .protocol import (
    Directive,
    GlobalStateUpdate,
    Heartbeat,
    HeartbeatResponse,
    HeldInputJack,
    HeldOutputJack,
    LocalState,
    RequestVote,
    RequestVoteResponse,
    Halt,
    SnapshotRequest,
    SnapshotResponse,
    PatchConnection,
    SetPreset,
    SetInputJack,
    SetOutputJack,
)


class Module:
    """The ``Module`` object mediates all of the patching and dataflow between all other modules on
    the network. Typically, a module only needs to be written as a processor on the input state to
    the output state and handle the associated user interface. Ideally, most of this would be placed
    on the python module level rather than the class level, but it is included here in order to
    maintain parity with the C++/static implementation.

    :param name: The human-readable name of the module

    :param event_handler: Instance of an ``EventHandler`` used to process application events. The
        application should either create its own class that inherits from ``EventHandler`` or create
        a new instance and modify the class methods.

    :param id: Unique identifier of the module. This should be of the form
        ``"group:product:instance_number"``, but anything that is globally unique works as well. In
        the physical world, this is unique for each module and is used to identify a specific one in
        the case of saving and restoring presets.
    """

    def __init__(
        self,
        name: str,
        event_handler: EventHandler = None,
        id: str = None,
    ):
        self.name = name
        self.event_handler = event_handler or EventHandler()
        self.uuid: str = id or str(uuid.uuid4())
        self.patch_state = PatchState.IDLE

        self.inputs: Dict[int, InputJack] = {}
        self.outputs: Dict[int, OutputJack] = {}
        self.broadcast_addr = None
        self.tick_time = None

        addresses = []
        for interface in netifaces.interfaces():
            interfaces_details = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in interfaces_details:
                for detail in interfaces_details[netifaces.AF_INET]:
                    addresses.append(detail)
                    logging.info("Address found: " + str(detail))

        if len(addresses) == 0:
            return

        self.broadcast_addr = addresses[0]
        for detail in addresses:
            if detail["broadcast"] == PREFERRED_BROADCAST:
                self.broadcast_addr = detail

        self.patch_server = PatchServer(self.uuid, self.broadcast_addr["addr"])
        self.leader_election = LeaderElection(self.uuid, self.patch_server)

    def update(self):
        """Process all pending tasks: send and recieve directives, audio and control data and
        perform callbacks if requested. This should be run periodically in an event loop or a
        thread.
        """
        if self.tick_time is None:
            self.tick_time = time.perf_counter()
        while (message := self.patch_server.get_message()) is not None:
            self.event_process(message)
        dt = time.perf_counter() - self.tick_time
        while dt > (1 / PACKET_RATE):
            for jack in self.inputs.values():
                jack.update()
            self.block_create()
            self.leader_election.update(None)
            self.tick_time += 1 / PACKET_RATE
            dt = time.perf_counter() - self.tick_time

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
        jack = OutputJack(self.broadcast_addr["addr"], name, color)
        self.outputs[jack.id] = jack
        return jack

    def get_jack_color(self, jack: Jack) -> int:
        """Returns the assigned HSV hue of the jack"""
        return jack.get_color()

    def get_jack_level(self, jack: Jack) -> float:
        """Returns the magnitude of the data last sent or recieved over this jack. For
        jacks operating at audio rates, this returns the maximum value over a single block.

        :param jack: The specific jack instance

        :return: Value from 0 to 1
        """
        return jack.get_level()

    def get_patch_state(self) -> PatchState:
        """Retrieves the global patch state"""
        return self.patch_state

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
            HeldInputJack(uuid=self.uuid, id=jack.id)
            for jack in self.inputs.values()
            if jack.patch_enabled
        ]
        held_outputs = [
            HeldOutputJack(
                uuid=self.uuid,
                id=jack.id,
                color=jack.color,
                addr=jack.endpoint[0],
                port=jack.endpoint[1],
            )
            for jack in self.outputs.values()
            if jack.patch_enabled
        ]
        self.leader_election.update_local_state(LocalState(held_inputs, held_outputs))

    def halt_callback(self) -> None:
        self.event_handler.halt()

    def halt_all(self) -> None:
        """Sends a halt directive to all connected modules"""
        self.patch_server.message_send(Halt(uuid="GLOBAL"))

    def update_patch_state(self, gsu: GlobalStateUpdate):
        """Manages changes in the global state"""

        self.patch_state = gsu.patch_state

        for in_jack in self.inputs.values():
            in_jack.patch_member = False
        for out_jack in self.outputs.values():
            out_jack.patch_member = False

        if gsu.patch_state == PatchState.PATCH_ENABLED:
            if gsu.input is not None:
                if self.uuid == gsu.input.uuid:
                    self.inputs[gsu.input.id].patch_member = True
                for out_jack in self.outputs.values():
                    out_jack.patch_member = out_jack.is_connected(
                        gsu.input.uuid, gsu.input.id
                    )
            elif gsu.output is not None:
                if self.uuid == gsu.output.uuid:
                    self.outputs[gsu.output.id].patch_member = True
                for in_jack in self.inputs.values():
                    in_jack.patch_member = in_jack.is_connected(
                        gsu.output.uuid, gsu.output.id
                    )
            else:
                logging.info("Invalid patch state received: " + str(gsu))

        if gsu.patch_state == PatchState.PATCH_TOGGLED:
            if gsu.input is None or gsu.output is None:
                logging.info("Invalid patch state received: " + str(gsu))
            else:
                for output_jack in self.outputs.values():
                    if gsu.output.uuid == self.uuid and gsu.output.id == output_jack.id:
                        continue
                    if output_jack.is_connected(gsu.input.uuid, gsu.input.id):
                        output_jack.disconnect(gsu.input.uuid, gsu.input.id)

                if gsu.input.uuid == self.uuid:
                    self.toggle_input_connection(gsu.input, gsu.output)
                if gsu.output.uuid == self.uuid:
                    self.toggle_output_connection(gsu.input, gsu.output)

        self.event_handler.patch(gsu.patch_state)

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
                output.addr,
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

    def block_create(self) -> None:
        """Gathers all input data into a single matrix for block processing"""

        num_inputs = len(self.inputs)
        num_outputs = len(self.outputs)
        result = np.zeros((num_inputs, BLOCK_SIZE, CHANNELS), dtype=SAMPLE_TYPE)
        for i, in_jack in enumerate(self.inputs.values()):
            result[i, :, :] = in_jack.get_data()
        post_process = self.event_handler.process(result)
        if num_outputs > 0:
            assert post_process.shape == (
                num_outputs,
                BLOCK_SIZE,
                CHANNELS,
            )
            assert post_process.dtype == SAMPLE_TYPE
            for i, out_jack in enumerate(self.outputs.values()):
                out_jack.send(post_process[i, :, :])

    def event_process(self, message: Directive):
        """Primary event handler for messages on the patching port"""

        if isinstance(message, Halt):
            self.halt_callback()

        if isinstance(message, SnapshotRequest):
            patches = []
            for id, in_jack in self.inputs.items():
                if in_jack.is_patched():
                    patches.append(
                        PatchConnection(
                            input_uuid=self.uuid,
                            input_jack_id=id,
                            output_uuid=in_jack.connected_jack_uuid,
                            output_jack_id=in_jack.connected_jack_id,
                        )
                    )
            for id, out_jack in self.outputs.items():
                for input_uuid, input_jack_id in out_jack.connected_jacks:
                    patches.append(
                        PatchConnection(
                            input_uuid=input_uuid,
                            input_jack_id=input_jack_id,
                            output_uuid=self.uuid,
                            output_jack_id=id,
                        )
                    )
            self.patch_server.message_send(
                SnapshotResponse(
                    uuid=self.uuid,
                    data=self.event_handler.get_snapshot(),
                    patched=patches,
                )
            )

        if isinstance(message, SnapshotResponse):
            self.event_handler.recieved_snapshot(
                message.uuid,
                message.to_json(),
            )

        if isinstance(message, SetPreset):
            logging.info("Got preset: " + str(message))
            for d in message.data:
                if d.uuid == self.uuid:
                    return self.prepare_preset(d)
            for in_jack in self.inputs.values():
                in_jack.clear()
            for out_jack in self.outputs.values():
                out_jack.clear()

        if isinstance(message, SetInputJack):
            if message.connection.input_uuid == self.uuid:
                self.inputs[message.connection.input_jack_id].connect(
                    self.broadcast_addr["addr"],
                    message.source.addr,
                    message.source.port,
                    message.source.color,
                    message.connection.output_uuid,
                    message.connection.output_jack_id,
                )

        if isinstance(message, SetOutputJack):
            if message.connection.output_uuid == self.uuid:
                self.outputs[message.connection.output_jack_id].connect(
                    message.connection.input_uuid,
                    message.connection.input_jack_id,
                )

        if (
            isinstance(message, Heartbeat)
            or isinstance(message, HeartbeatResponse)
            or isinstance(message, RequestVote)
            or isinstance(message, RequestVoteResponse)
        ):
            self.leader_election.update(message)

        if isinstance(message, GlobalStateUpdate):
            logging.info("<= " + str(message))
            self.update_patch_state(message)

    def get_all_snapshots(self):
        """Send a snapshot request to all modules"""
        self.patch_server.message_send(SnapshotRequest(uuid=self.uuid))

    def set_all_snapshots(self, snapshots: List[bytes]):
        """Send a changed present message to all modules"""
        if self.get_patch_state() != PatchState.IDLE:
            return
        data = [SnapshotResponse.from_json(s) for s in snapshots]
        self.patch_server.message_send(SetPreset(uuid=self.uuid, data=data))

    def prepare_preset(self, d: SnapshotResponse):
        self.event_handler.set_snapshot(d.data)
        input_patches = {}
        output_patches = defaultdict(list)
        for p in d.patched:
            if p.input_uuid == self.uuid:
                input_patches[p.input_jack_id] = p
            if p.output_uuid == self.uuid:
                output_patches[p.output_jack_id].append(p)

        for id, in_jack in self.inputs.items():
            if in_jack.is_patched():
                if id not in input_patches or (
                    not in_jack.is_connected(
                        input_patches[id].output_uuid, input_patches[id].output_jack_id
                    )
                ):
                    in_jack.clear()

        for id, out_jack in self.outputs.items():
            out_jack.clear()
            for p in output_patches[id]:
                out_jack.connect(p.input_uuid, p.input_jack_id)
                self.patch_server.message_send(
                    SetInputJack(
                        uuid=self.uuid,
                        source=HeldOutputJack(
                            uuid=self.uuid,
                            id=id,
                            color=out_jack.color,
                            addr=out_jack.endpoint[0],
                            port=out_jack.endpoint[1],
                        ),
                        connection=p,
                    )
                )
