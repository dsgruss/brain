import numpy as np

from typing import Final

#: Preferred communication subnet in case multiple network interfaces are present
PREFERRED_BROADCAST: Final = "10.255.255.255"

#: Port used to establish the global state and create new patch connections
PATCH_PORT: Final = 19874

#: Frequency in packets per second to send audio and CV data
PACKET_RATE: Final = 1000

#: Audio sample rate in Hz (must be a multiple of ``PACKET_RATE``)
SAMPLE_RATE: Final = 48000

#: Number of samples in a full-length packet (``SAMPLE_RATE`` / ``PACKET_RATE``)
BLOCK_SIZE: Final = 48

#: Number of independent audio processing channels
CHANNELS: Final = 8

#: Maximum number of states to buffer
BUFFER_SIZE: Final = 100

#: Sample data type
SAMPLE_TYPE: Final = np.int16
