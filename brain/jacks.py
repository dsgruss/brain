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
        self.id: Final = str(next(Jack._id_iter))

    def is_patched(self) -> bool:
        raise NotImplementedError

    def get_color(self) -> int:
        raise NotImplementedError


class InputJack(Jack):
    """An input jack which receives data from an output jack over the network. This is not
    typically instantiated directly but rather through ``Module.add_input``.

    :param name: Identifier describing the input jack

    :param data_callback: Function that is called when new data arrives at the input jack. This
        callback fires immediately when the data is received, so use ``process_callback`` if a
        synchronized consumption of multiple inputs is desired (i.e. the signals are not processed
        independently).
    """

    def __init__(self, name: str, data_callback):
        self.callback = data_callback
        self.data_queue = deque()
        self.last_seen_data = np.zeros((BLOCK_SIZE, CHANNELS), dtype=SAMPLE_TYPE)
        self.connected_jack = None
        self.jack_listener = InputJackListener()

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
        if (data := self.jack_listener.get_data()) is not None:
            if self.callback is not None:
                self.callback(data)
            data = np.frombuffer(data, dtype=SAMPLE_TYPE)
            data = data.reshape((len(data) // CHANNELS, CHANNELS))
            self.last_seen_data = data.copy()
            self.data_queue.appendleft(data)
            return True
        return False

    def get_data(self) -> np.ndarray:
        """Pull pending data from the jack. In the event that data is not available, this will
        return a copy of the last seen packet. Used in response to a ``process_callback``.

        :return: An array of shape (X, ``CHANNELS``) of data type ``SAMPLE_TYPE``,
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
