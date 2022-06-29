import numpy as np

from typing import Final

#: Preferred communication subnet in case multiple network interfaces are present
PREFERRED_BROADCAST: Final = "10.255.255.255"

#: Multicast address used for patching and systems communication
PATCH_ADDR: Final = "239.0.0.0"

#: Port used to establish the global state and create new patch connections
PATCH_PORT: Final = 19874

#: Port used for audio data communications
JACK_PORT: Final = 19991

#: Frequency in packets per second to send audio and CV data
PACKET_RATE: Final = 1000

#: Audio sample rate in Hz (must be a multiple of ``PACKET_RATE``)
SAMPLE_RATE: Final = 48000

#: Number of samples in a full-length packet (``SAMPLE_RATE`` / ``PACKET_RATE``)
BLOCK_SIZE: Final = 48

#: Number of independent audio processing channels
CHANNELS: Final = 8

#: Maximum number of states to buffer
BUFFER_SIZE: Final = 1

#: Sample data type
SAMPLE_TYPE: Final = np.int16


def midi_note_to_voct(note):
    """Translates a MIDI note number to V/Oct value"""
    return (note - 69) * 512


def voct_to_frequency(v_oct):
    """Translates a V/Oct value to frequency in Hz"""
    return 440 * voct_to_freq_scale(v_oct)


def voct_to_freq_scale(v_oct):
    """Translates a V/Oct value to a scale value"""
    return 2 ** (v_oct / (512 * 12))
