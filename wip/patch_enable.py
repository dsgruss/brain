import numpy as np
import time

from brain.constants import BLOCK_SIZE, CHANNELS, JACK_PORT, SAMPLE_TYPE
from brain.protocol import HeldOutputJack, LocalState, PatchConnection, SetInputJack, Update
from brain.servers import OutputJackServer, PatchServer

p = PatchServer("test_control", "10.0.0.2")
p.message_send(Update("test_control", LocalState([], [])))
exit(0)
p.message_send(
    SetInputJack("test_control",
    HeldOutputJack("test_control", "1", 30, "239.8.7.6", JACK_PORT),
    PatchConnection("you", "1", "test_control", "1")))

o = OutputJackServer("10.0.0.2", "239.8.7.6")
d = (np.random.random_sample((BLOCK_SIZE, CHANNELS)) * 16000).astype(SAMPLE_TYPE)

time.sleep(1)

o.datagram_send(d.tobytes())