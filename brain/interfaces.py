from enum import auto, Enum
from typing import NewType


class PatchState(Enum):
    """Enum used to track a global state over all connected modules"""

    IDLE = auto()  #: No buttons pushed across all modules
    PATCH_ENABLED = auto()  #: One single button pushed
    PATCH_TOGGLED = auto()  #: Two buttons pushed, consisting of an input and output
    BLOCKED = auto()  #: Three or more buttons pushed or two of the same type


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

    def halt(self) -> None:
        """Shutdown directive"""
        pass
