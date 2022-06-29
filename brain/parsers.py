import json

from typing import Optional
from .protocol import (
    Directive,
    Update,
    SnapshotRequest,
    SnapshotResponse,
    SetPreset,
    SetInputJack,
    Halt,
    Heartbeat,
    HeartbeatResponse,
    RequestVote,
    RequestVoteResponse,
)


class MessageParser:
    """Determines how the messages passed on the patching port get translated into raw bytes in the
    udp packets.
    """

    def parse_directive(self, data: bytes) -> Optional[Directive]:
        """Turns raw bytes into a ``Directive``. Returns ``None`` if the message was unable to be
        parsed.

        :param data: Raw data

        :return: The message object or ``None``
        """
        if data == b"":
            return None
        else:
            resp = json.loads(data)
            if "Update" in resp:
                return Update.from_dict(resp["Update"])
            if "SnapshotRequest" in resp:
                return SnapshotRequest.from_dict(resp["SnapshotRequest"])
            if "SnapshotResponse" in resp:
                return SnapshotResponse.from_dict(resp["SnapshotResponse"])
            if "SetPreset" in resp:
                return SetPreset.from_dict(resp["SetPreset"])
            if "SetInputJack" in resp:
                return SetInputJack.from_dict(resp["SetInputJack"])
            if "Halt" in resp:
                return Halt.from_dict(resp["Halt"])

            if "Heartbeat" in resp:
                return Heartbeat.from_dict(resp["Heartbeat"])
            if "HeartbeatResponse" in resp:
                return HeartbeatResponse.from_dict(resp["HeartbeatResponse"])
            if "RequestVote" in resp:
                return RequestVote.from_dict(resp["RequestVote"])
            if "RequestVoteResponse" in resp:
                return RequestVoteResponse.from_dict(resp["RequestVoteResponse"])
            return None

    def create_directive(self, message: Directive) -> bytes:
        """Inverse of ``parse_directive``"""

        resp = message.to_dict()
        if isinstance(message, Update):
            return json.dumps({"Update": resp}).encode()
        if isinstance(message, SnapshotRequest):
            return json.dumps({"SnapshotRequest": resp}).encode()
        if isinstance(message, SnapshotResponse):
            return json.dumps({"SnapshotResponse": resp}).encode()
        if isinstance(message, SetPreset):
            return json.dumps({"SetPreset": resp}).encode()
        if isinstance(message, SetInputJack):
            return json.dumps({"SetInputJack": resp}).encode()
        if isinstance(message, Halt):
            return json.dumps({"Halt": resp}).encode()

        if isinstance(message, Heartbeat):
            return json.dumps({"Heartbeat": resp}).encode()
        if isinstance(message, HeartbeatResponse):
            return json.dumps({"HeartbeatResponse": resp}).encode()
        if isinstance(message, RequestVote):
            return json.dumps({"RequestVote": resp}).encode()
        if isinstance(message, RequestVoteResponse):
            return json.dumps({"RequestVoteResponse": resp}).encode()
        return b""
