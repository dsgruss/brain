import json
import mido
import netifaces
import numpy as np
import socket
import ssdp
import threading
import time

from operator import itemgetter
from struct import unpack


class Envgen:
    # Promote midi stream to audio rate CV, streaming over ethernet
    channels = 8
    updatefreq = 1000  # Hz
    atime = 0.05  # sec
    rtime = 0.25  # sec
    timestamp = 0
    sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

    directive_port = 10000
    uuid = "078e6915-945f-4071-8578-4cd459056099"

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

    interfaces = []

    def __init__(self):
        print("Opening all midi inputs by default...")
        for inp in mido.get_input_names():
            mido.open_input(inp, callback=self.midi_to_cv_callback)

        print("Discovering network interfaces...")
        for interface in netifaces.interfaces():
            interfaces_details = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in interfaces_details:
                self.interfaces.extend(interfaces_details[netifaces.AF_INET])

        for interface in self.interfaces:
            threading.Thread(
                target=self.control_thread, args=(interface["addr"],), daemon=True
            ).start()
        time.sleep(1)
        for interface in self.interfaces:
            threading.Thread(
                target=ssdp.ssdp_client_thread,
                args=(interface["addr"], self.directive_port, self.uuid),
                daemon=True,
            ).start()
        threading.Thread(target=self.output_thread, daemon=True).start()

    def midi_to_cv_callback(self, message: mido.Message):
        print(message)
        self.timestamp += 1
        if message.type == "note_off":
            for v in self.voices:
                if v["note"] == message.note and v["on"]:
                    v["on"] = False
                    v["timestamp"] = self.timestamp
        elif message.type == "note_on":
            # First see if we can take the oldest voice that has been released
            voices_off = sorted(
                (v for v in self.voices if v["on"] == False),
                key=itemgetter("timestamp"),
            )
            if len(voices_off) > 0:
                voices_off[0]["note"] = message.note
                voices_off[0]["on"] = True
                voices_off[0]["timestamp"] = self.timestamp
            else:
                # Otherwise, steal a voice. In this case, take the oldest note played. We
                # also have a choice of whether to just change the pitch (done here), or to
                # shut the note off and retrigger.
                voice_steal = sorted(
                    (v for v in self.voices), key=itemgetter("timestamp")
                )[0]
                voice_steal["note"] = message.note
                voice_steal["timestamp"] = self.timestamp
        for v in self.voices:
            print("\t", v)

    def output_thread(self):
        # Send the data as CV over over all requested ports and addresses at the configured sample rate

        while True:
            currtime = time.time()
            rtp_header = bytes("############", "ASCII")
            voct_data = np.zeros((1, 8), dtype=np.int16)
            gate_data = np.zeros((1, 8), dtype=np.int16)
            level_data = np.zeros((1, 8), dtype=np.int16)
            for i, v in enumerate(self.voices):
                voct_data[0, i] = v["note"] * 256
                gate_data[0, i] = 16000 if v["on"] else 0
                if gate_data[0, i] > v["env"]:
                    v["env"] = min(
                        gate_data[0, i],
                        v["env"] + (currtime - v["envupdate"]) / self.atime * 16000,
                    )
                else:
                    v["env"] = max(
                        gate_data[0, i],
                        v["env"] - (currtime - v["envupdate"]) / self.rtime * 16000,
                    )
                level_data[0, i] = v["env"]
                v["envupdate"] = currtime
            for loc in self.notedest:
                self.sock.sendto(rtp_header + voct_data.tobytes(), loc)
            for loc in self.gatedest:
                self.sock.sendto(rtp_header + gate_data.tobytes(), loc)
            for loc in self.asredest:
                self.sock.sendto(rtp_header + level_data.tobytes(), loc)
            dtime = time.time() - currtime
            if dtime > (1 / self.updatefreq):
                continue
            else:
                time.sleep((1 / self.updatefreq) - dtime)

    def control_thread(self, local_address):
        # Thread that responds to identification and control commands

        sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

        for _ in range(10):
            try:
                sock.bind((local_address, self.directive_port))
                break
            except OSError:
                self.directive_port += 1
                continue
        else:
            print("Unable to find open port.")
            exit(-1)

        env = {
            "name": "Midi to CV converter",
            "id": self.uuid,
            "inputs": [],
            "outputs": [
                {
                    "id": 0,
                    "name": "Note",
                    "channels": self.channels,
                    "samplerate": self.updatefreq,
                    "format": "L16",
                },
                {
                    "id": 1,
                    "name": "Gate",
                    "channels": self.channels,
                    "samplerate": self.updatefreq,
                    "format": "L16",
                },
                {
                    "id": 2,
                    "name": "Velocity",
                    "channels": self.channels,
                    "samplerate": self.updatefreq,
                    "format": "L16",
                },
                {
                    "id": 3,
                    "name": "Lift",
                    "channels": self.channels,
                    "samplerate": self.updatefreq,
                    "format": "L16",
                },
                {
                    "id": 4,
                    "name": "Pitch Wheel",
                    "channels": 1,
                    "samplerate": self.updatefreq,
                    "format": "L16",
                },
                {
                    "id": 5,
                    "name": "Mod Wheel",
                    "channels": 1,
                    "samplerate": self.updatefreq,
                    "format": "L16",
                },
                {
                    "id": 6,
                    "name": "ASR Envelope",
                    "channels": self.channels,
                    "samplerate": self.updatefreq,
                    "format": "L16",
                },
            ],
        }

        print(f"Listening for directives on {local_address}:{self.directive_port}...")

        while True:
            msg, addr = sock.recvfrom(1500)
            if msg.startswith(b"IDENTIFY"):
                print("Identification command received.")
                sock.sendto(bytes(json.dumps(env), "utf8"), addr)
            elif msg.startswith(b"REQUEST"):
                print("Patch mapping command received.")
                directive, destination_address, destination_port, id = unpack(
                    "!10s4shB", msg
                )
                address = (socket.inet_ntoa(destination_address), destination_port)
                if id == 0:
                    self.notedest.append(address)
                elif id == 1:
                    self.gatedest.append(address)
                elif id == 2:
                    self.velodest.append(address)
                elif id == 3:
                    self.liftdest.append(address)
                elif id == 4:
                    self.piwhdest.append(address)
                elif id == 5:
                    self.mdwhdest.append(address)
                elif id == 6:
                    self.asredest.append(address)
            elif msg.startswith(b"RESET"):
                print("Reset command received.")
                self.notedest.clear()
                self.gatedest.clear()
                self.velodest.clear()
                self.liftdest.clear()
                self.piwhdest.clear()
                self.mdwhdest.clear()
                self.asredest.clear()


if __name__ == "__main__":
    e = Envgen()
    while True:
        time.sleep(1)
