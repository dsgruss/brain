import json

from enum import Enum, auto
from dataclasses import dataclass
from typing import Union

from brain.interfaces import HeldInputJack, HeldOutputJack, LocalState, ModuleUuid


class MessageType(Enum):
    UPDATE = auto()
    HALT = auto()


@dataclass
class Message:
    uuid: ModuleUuid
    type: MessageType
    local_state: Union[LocalState, None] = None


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
            return Message(response["uuid"], MessageType.UPDATE, state)
        if response["message"] == "HALT":
            return Message(response["uuid"], MessageType.HALT)
        return None

    def create_directive(self, message: Message) -> bytes:
        """Inverse of ``parse_directive``"""

        if message.type == MessageType.HALT:
            json_msg = {"message": "HALT", "uuid": message.uuid}
            return bytes(json.dumps(json_msg), "utf8")
        if message.type == MessageType.UPDATE:
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
        raise NotImplementedError