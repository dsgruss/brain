import json

from dataclasses import dataclass
from typing import List, Union

from brain.interfaces import (
    HeldInputJack,
    HeldOutputJack,
    LocalState,
    ModuleUuid,
    PatchConnection,
)


@dataclass
class Message:
    uuid: ModuleUuid


@dataclass
class Update(Message):
    local_state: LocalState


@dataclass
class SnapshotRequest(Message):
    pass


@dataclass
class SnapshotResponse(Message):
    data: bytes
    patched: List[PatchConnection]


@dataclass
class Halt(Message):
    pass


class MessageParser:
    """Determines how the messages passed on the patching port get translated into raw bytes in the
    udp packets.
    """

    def parse_directive(self, data: bytes) -> Union[Message, None]:
        """Turns raw bytes into a ``Message``. Returns ``None`` if the message was unable to be
        parsed.

        :param data: Raw data

        :return: The message object or ``None``
        """
        try:
            response = json.loads(data)
        except json.JSONDecodeError:
            return None
        if any(k not in response for k in ("message", "uuid")):
            return None

        if response["message"] == "UPDATE":
            if "state" not in response:
                return None
            state = LocalState(list(), list())
            for d in response["state"].get("inputs") or []:
                if any(k not in d for k in ("id",)):
                    return None
                state.held_inputs.append(HeldInputJack(response["uuid"], d["id"]))
            for d in response["state"].get("outputs") or []:
                if any(k not in d for k in ("id", "color", "port")):
                    return None
                state.held_outputs.append(
                    HeldOutputJack(response["uuid"], d["id"], d["color"], d["port"])
                )
            return Update(response["uuid"], state)

        if response["message"] == "SNAPSHOTREQUEST":
            return SnapshotRequest(response["uuid"])

        if response["message"] == "SNAPSHOTRESPONSE":
            return SnapshotResponse(
                response["uuid"],
                response["data"].encode(),
                [
                    PatchConnection(
                        p["input_uuid"],
                        p["input_jack_id"],
                        p["output_uuid"],
                        p["output_jack_id"],
                    )
                    for p in response["patched"]
                ],
            )

        if response["message"] == "HALT":
            return Halt(response["uuid"])
        return None

    def create_directive(self, message: Message) -> bytes:
        """Inverse of ``parse_directive``"""

        if isinstance(message, Halt):
            json_msg = {"message": "HALT", "uuid": message.uuid}
            return bytes(json.dumps(json_msg), "utf8")

        if isinstance(message, Update):
            if message.local_state is None:
                raise ValueError
            inputs = [{"id": j.id} for j in message.local_state.held_inputs]
            outputs = [
                {"id": j.id, "color": j.color, "port": j.port}
                for j in message.local_state.held_outputs
            ]
            json_msg = {
                "message": "UPDATE",
                "uuid": message.uuid,
                "state": {"inputs": inputs, "outputs": outputs},
            }
            return bytes(json.dumps(json_msg), "utf8")

        if isinstance(message, SnapshotRequest):
            json_msg = {"message": "SNAPSHOTREQUEST", "uuid": message.uuid}
            return bytes(json.dumps(json_msg), "utf8")

        if isinstance(message, SnapshotResponse):
            patched = [
                {
                    "input_uuid": p.input_uuid,
                    "input_jack_id": p.input_jack_id,
                    "output_uuid": p.output_uuid,
                    "output_jack_id": p.output_jack_id,
                }
                for p in message.patched
            ]
            json_msg = {
                "message": "SNAPSHOTRESPONSE",
                "uuid": message.uuid,
                "data": message.data.decode(),
                "patched": patched,
            }
            return bytes(json.dumps(json_msg), "utf8")

        raise NotImplementedError
