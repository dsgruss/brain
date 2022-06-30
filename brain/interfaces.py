import numpy as np

from brain.constants import BLOCK_SIZE, CHANNELS, SAMPLE_TYPE
from brain.protocol import PatchState


class EventHandler:
    """Events to be handled by the application"""

    def patch(self, state: PatchState) -> None:
        """Global patch state has changed

        :param state: The new state of the modules
        """
        pass

    def process(self, input: np.ndarray) -> np.ndarray:
        """Process all incoming data as a single block

        :param input: An array of shape (X, ``BLOCK_SIZE``, ``CHANNELS``) of data type
            ``SAMPLE_TYPE``, where X is the number of added input jacks in the order created.

        :return: An array of shape (X, ``BLOCK_SIZE``, ``CHANNELS``) of data type ``SAMPLE_TYPE``,
            where X is the number of added output jacks in the order created.
        """
        return np.zeros((0, BLOCK_SIZE, CHANNELS), dtype=SAMPLE_TYPE)

    def get_snapshot(self) -> str:
        """Return the current state of the module without patches for preset saving. The structure
        of the data is up to the module implementation and will be used for ``set_snapshot``.
        """
        return ""

    def recieved_snapshot(self, id: str, snapshot: str) -> None:
        """Called when module recieves a complete snapshot of another including patch information.
        Setup by ``get_all_snapshots``.
        """
        pass

    def set_snapshot(self, snapshot: str) -> None:
        """Sets the state of the module to a previously taken snapshot."""
        pass

    def halt(self) -> None:
        """Shutdown directive"""
        pass
