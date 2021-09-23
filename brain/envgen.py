import json
import mido
import numpy as np
import socket
import threading
import time

from operator import itemgetter
from struct import unpack

# Promote midi stream to audio rate CV, streaming over ethernet
channels = 8
updatefreq = 1000  # Hz
atime = 0.25  # sec
rtime = 1.00  # sec
timestamp = [0]
sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

voices = [
    {"note": 0, "on": False, "timestamp": 0, "env": 0, "envupdate": time.time()}
    for _ in range(channels)
]

# List of destination address:ports configured for each output

notedest = []
gatedest = []
velodest = []
liftdest = []
piwhdest = []
mdwhdest = []
asredest = []


def midi_to_cv_callback(message: mido.Message):
    timestamp[0] += 1
    if message.type == "note_off":
        for v in voices:
            if v["note"] == message.note and v["on"]:
                v["on"] = False
                v["timestamp"] = timestamp[0]
    elif message.type == "note_on":
        # First see if we can take the oldest voice that has been released
        voices_off = sorted(
            (v for v in voices if v["on"] == False),
            key=itemgetter("timestamp"),
        )
        if len(voices_off) > 0:
            voices_off[0]["note"] = message.note
            voices_off[0]["on"] = True
            voices_off[0]["timestamp"] = timestamp[0]
        else:
            # Otherwise, steal a voice. In this case, take the oldest note played. We
            # also have a choice of whether to just change the pitch (done here), or to
            # shut the note off and retrigger.
            voice_steal = sorted((v for v in voices), key=itemgetter("timestamp"))[0]
            voice_steal["note"] = message.note
            voice_steal["timestamp"] = timestamp[0]


def output_thread():
    # Send the data as CV over over all requested ports and addresses at the configured sample rate

    while True:
        currtime = time.time()
        rtp_header = bytes("############", "ASCII")
        voct_data = np.zeros((1, 8), dtype=np.int16)
        gate_data = np.zeros((1, 8), dtype=np.int16)
        level_data = np.zeros((1, 8), dtype=np.int16)
        for i, v in enumerate(voices):
            voct_data[0, i] = v["note"] * 256
            gate_data[0, i] = 16000 if v["on"] else 0
            if gate_data[0, i] > v["env"]:
                v["env"] = min(
                    gate_data[0, i],
                    v["env"] + (currtime - v["envupdate"]) / atime * 16000,
                )
            else:
                v["env"] = max(
                    gate_data[0, i],
                    v["env"] - (currtime - v["envupdate"]) / rtime * 16000,
                )
            level_data[0, i] = v["env"]
            v["envupdate"] = currtime
        for loc in notedest:
            sock.sendto(rtp_header + voct_data.tobytes(), loc)
        for loc in gatedest:
            sock.sendto(rtp_header + gate_data.tobytes(), loc)
        for loc in asredest:
            sock.sendto(rtp_header + level_data.tobytes(), loc)
        dtime = time.time() - currtime
        if dtime > (1 / updatefreq):
            continue
        else:
            time.sleep((1 / updatefreq) - dtime)


print("Opening all midi inputs by default.")
for inp in mido.get_input_names():
    mido.open_input(inp, callback=midi_to_cv_callback)


def control_thread():
    # Thread that responds to identification broadcasts and control commands

    sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 10000))

    env = {
        "name": "Midi to CV converter",
        "inputs": [],
        "outputs": [
            {
                "id": 0,
                "name": "Note",
                "channels": channels,
                "samplerate": updatefreq,
                "format": "L16",
            },
            {
                "id": 1,
                "name": "Gate",
                "channels": channels,
                "samplerate": updatefreq,
                "format": "L16",
            },
            {
                "id": 2,
                "name": "Velocity",
                "channels": channels,
                "samplerate": updatefreq,
                "format": "L16",
            },
            {
                "id": 3,
                "name": "Lift",
                "channels": channels,
                "samplerate": updatefreq,
                "format": "L16",
            },
            {
                "id": 4,
                "name": "Pitch Wheel",
                "channels": 1,
                "samplerate": updatefreq,
                "format": "L16",
            },
            {
                "id": 5,
                "name": "Mod Wheel",
                "channels": 1,
                "samplerate": updatefreq,
                "format": "L16",
            },
            {
                "id": 6,
                "name": "ASR Envelope",
                "channels": channels,
                "samplerate": updatefreq,
                "format": "L16",
            },
        ],
    }

    print("Listening for directives on port 10000...")

    while True:
        msg, addr = sock.recvfrom(1500)
        if msg.startswith(b"IDENTIFY"):
            print("Identification command received.")
            sock.sendto(bytes(json.dumps(env), "utf8"), addr)
        elif msg.startswith(b"REQUEST"):
            directive, destination_address, destination_port, id = unpack(
                "!10s4shB", msg
            )
            address = (socket.inet_ntoa(destination_address), destination_port)
            if id == 0:
                notedest.append(address)
            elif id == 1:
                gatedest.append(address)
            elif id == 2:
                velodest.append(address)
            elif id == 3:
                liftdest.append(address)
            elif id == 4:
                piwhdest.append(address)
            elif id == 5:
                mdwhdest.append(address)
            elif id == 6:
                asredest.append(address)


threading.Thread(target=control_thread, daemon=True).start()
threading.Thread(target=output_thread, daemon=True).start()
while True:
    pass
