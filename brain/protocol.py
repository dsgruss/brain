from dataclasses import dataclass
from dataclasses_json import DataClassJsonMixin
from enum import Enum
from typing import List, Optional

# Convenience structures for defining current patching states and connections


class PatchState(Enum):
    """Enum used to track a global state over all connected modules"""

    IDLE = 0  #: No buttons pushed across all modules
    PATCH_ENABLED = 1  #: One single button pushed
    PATCH_TOGGLED = 2  #: Two buttons pushed, consisting of an input and output
    BLOCKED = 3  #: Three or more buttons pushed or two of the same type


@dataclass
class HeldInputJack(DataClassJsonMixin):
    uuid: str
    id: str


@dataclass
class HeldOutputJack(DataClassJsonMixin):
    uuid: str
    id: str
    color: int
    addr: str
    port: int


@dataclass
class LocalState(DataClassJsonMixin):
    held_inputs: List[HeldInputJack]
    held_outputs: List[HeldOutputJack]


@dataclass
class PatchConnection(DataClassJsonMixin):
    input_uuid: str
    input_jack_id: str
    output_uuid: str
    output_jack_id: str


# Patch update and preset handling messages


@dataclass
class Directive(DataClassJsonMixin):
    pass


@dataclass
class Update(Directive, DataClassJsonMixin):
    uuid: str
    local_state: LocalState


@dataclass
class SnapshotRequest(Directive, DataClassJsonMixin):
    uuid: str


@dataclass
class SnapshotResponse(Directive, DataClassJsonMixin):
    uuid: str
    data: str
    patched: List[PatchConnection]


@dataclass
class SetPreset(Directive, DataClassJsonMixin):
    uuid: str
    data: List[SnapshotResponse]


@dataclass
class SetInputJack(Directive, DataClassJsonMixin):
    uuid: str
    source: HeldOutputJack
    connection: PatchConnection


@dataclass
class SetOutputJack(Directive, DataClassJsonMixin):
    uuid: str
    source: HeldInputJack
    connection: PatchConnection


@dataclass
class Halt(Directive, DataClassJsonMixin):
    uuid: str


# Leader election and state sync


@dataclass
class Heartbeat(Directive, DataClassJsonMixin):
    uuid: str
    term: int
    iteration: int


@dataclass
class HeartbeatResponse(Directive, DataClassJsonMixin):
    uuid: str
    term: int
    success: bool
    iteration: Optional[int] = None
    state: Optional[LocalState] = None


@dataclass
class GlobalStateUpdate(Directive, DataClassJsonMixin):
    uuid: str
    patch_state: PatchState
    input: HeldInputJack
    output: HeldOutputJack


@dataclass
class RequestVote(Directive, DataClassJsonMixin):
    uuid: str
    term: int


@dataclass
class RequestVoteResponse(Directive, DataClassJsonMixin):
    uuid: str
    term: int
    voted_for: str
    vote_granted: bool
