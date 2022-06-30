import itertools
import logging
import numpy as np

from collections import deque
from typing import Final, Set, Tuple

from .constants import BLOCK_SIZE, CHANNELS, SAMPLE_TYPE
from .servers import InputJackListener, OutputJackServer


class Jack:
    patch_enabled = False
    patch_member = False
    _id_iter = itertools.count()

    def __init__(self, name: str):
        self.name: Final = name
        self.id: Final = next(Jack._id_iter)

    def is_patched(self) -> bool:
        raise NotImplementedError

    def get_color(self) -> int:
        raise NotImplementedError

    def get_level(self) -> float:
        raise NotImplementedError


class InputJack(Jack):
    """An input jack which receives data from an output jack over the network. This is not
    typically instantiated directly but rather through ``Module.add_input``.

    :param name: Identifier describing the input jack
    """

    def __init__(self, name: str):
        self.data_queue = deque()
        self.last_seen_data = np.zeros((BLOCK_SIZE, CHANNELS), dtype=SAMPLE_TYPE)
        self.connected_jack_uuid = None
        self.connected_jack_id = None
        self.jack_listener = InputJackListener()

        super().__init__(name)

    def is_patched(self) -> bool:
        """Check if input jack is currently connected to a patch

        :return: ``True`` if connected
        """
        return self.connected_jack_uuid is not None

    def clear(self):
        if self.is_patched():
            self.jack_listener.disconnect()
            self.connected_jack_uuid = None
            self.connected_jack_id = None

    def disconnect(self, output_uuid, output_id):
        if self.is_connected(output_uuid, output_id):
            self.clear()

    def is_connected(self, output_uuid, output_id):
        return (self.connected_jack_uuid, self.connected_jack_id) == (
            output_uuid,
            output_id,
        )

    def connect(self, address, mult_addr, port, output_color, output_uuid, output_id):
        if self.is_patched():
            self.clear()
        self.color = output_color
        self.connected_jack_uuid = output_uuid
        self.connect_jack_id = output_id

        self.jack_listener.connect(address, mult_addr, port)

    def update(self):
        if len(data := self.jack_listener.get_data()) != 0:
            data = np.frombuffer(data, dtype=SAMPLE_TYPE)
            data = data.reshape((len(data) // CHANNELS, CHANNELS))
            self.last_seen_data = data.copy()
            self.data_queue.appendleft(data)
            return True
        return False

    def get_data(self) -> np.ndarray:
        """Pull pending data from the jack. In the event that data is not available, this will
        return a copy of the last seen packet.

        :return: An array of shape (``BLOCK_SIZE``, ``CHANNELS``) of data type ``SAMPLE_TYPE``
        """
        if len(self.data_queue) > 0:
            return self.data_queue.pop()
        else:
            return self.last_seen_data.copy()

    def get_color(self) -> int:
        if not self.is_patched():
            return 330
        else:
            return self.color

    def get_level(self) -> float:
        if not self.is_patched():
            return 0
        else:
            return np.clip(np.amax(self.last_seen_data) / 8000, 0, 1)


class OutputJack(Jack):
    """An output jack which sends data to input jacks over the network. This is not
    typically instantiated directly but rather through ``Module.add_output``.

    :param address: Local ip4 address to use multicast

    :param name: Identifier describing the output jack

    :param color: An HSV Hue value for the jack's primary color in [0, 360). This color is
        propagated to any input jacks that it is patched to.
    """

    def __init__(self, address: str, name: str, color: int):
        self.color = color
        self.connected_jacks: Set[Tuple[str, int]] = set()
        self.jack_server = OutputJackServer(address)
        self.endpoint = self.jack_server.endpoint
        self.level = 0

        super().__init__(name)

    def send(self, data: np.ndarray) -> None:
        """Send data out through this jack. Caller is responsible for maintaining packet timing.
        Currently, this sends data out to the network at all times.

        :data: Data to be sent as an ndarray
        """
        self.level = np.amax(data)
        self.jack_server.datagram_send(data.tobytes())

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

    def get_level(self) -> float:
        return np.clip(self.level / 8000, 0, 1)
