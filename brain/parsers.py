from typing import Optional
from .proto.patching_pb2 import Directive


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
            m = Directive()
            m.ParseFromString(data)
            return m

    def create_directive(self, message: Directive) -> bytes:
        """Inverse of ``parse_directive``"""

        return message.SerializeToString()
