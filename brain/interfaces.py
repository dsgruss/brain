import numpy as np

from dataclasses import dataclass
from enum import auto, Enum
from typing import Dict, List, NewType


class PatchState(Enum):
    """Enum used to track a global state over all connected modules"""

    IDLE = auto()  #: No buttons pushed across all modules
    PATCH_ENABLED = auto()  #: One single button pushed
    PATCH_TOGGLED = auto()  #: Two buttons pushed, consisting of an input and output
    BLOCKED = auto()  #: Three or more buttons pushed or two of the same type


ModuleUuid = NewType("ModuleUuid", str)


@dataclass
class HeldInputJack:
    uuid: ModuleUuid
    id: str


@dataclass
class HeldOutputJack:
    uuid: ModuleUuid
    id: str
    color: int
    port: int


@dataclass
class LocalState:
    held_inputs: List[HeldInputJack]
    held_outputs: List[HeldOutputJack]


@dataclass
class GlobalState:
    """Describes the global state: all held buttons"""

    patch_state: PatchState
    held_inputs: Dict[ModuleUuid, List[HeldInputJack]]
    held_outputs: Dict[ModuleUuid, List[HeldOutputJack]]


@dataclass
class PatchConnection:
    input_uuid: ModuleUuid
    input_jack_id: str
    output_uuid: ModuleUuid
    output_jack_id: str


class EventHandler:
    """Events to be handled by the application"""

    def patch(self, state: PatchState) -> None:
        """Global patch state has changed

        :param state: The new state of the modules
        """
        pass

    def process(self) -> None:
        """Input jack data is ready to be processed. Event processing should use ``get_data`` on all
        input jacks to ensure the most synchronized state.
        """
        pass

    def block_process(self, input: np.ndarray) -> np.ndarray:
        """Process all incoming data as a single block

        :param input: An array of shape (Y, X, ``CHANNELS``) of data type ``SAMPLE_TYPE``, where X
            is the number of samples sent in a packet window and Y is the number of added input
            jacks in the order created. Data that is sent with a lower sample rate is expanded to
            match the highest sample rate packet.

        :return: An array of shape (Y, X, ``CHANNELS``) of data type ``SAMPLE_TYPE``, where X is the
            number of samples sent in a packet window and Y is the number of added output jacks in
            the order created.
        """
        return np.zeros(1)

    def get_snapshot(self) -> bytes:
        """Return the current state of the module without patches for preset saving. The structure
        of the data is up to the module implementation and will be used for ``set_snapshot``.
        """
        return b""

    def recieved_snapshot(self, snapshot) -> None:
        """Called when module recieves a snapshot of another. Setup by ``get_all_snapshots``."""
        pass

    def set_snapshot(self, snapshot: bytes) -> None:
        """Sets the state of the module to a previously taken snapshot."""
        pass

    def halt(self) -> None:
        """Shutdown directive"""
        pass
