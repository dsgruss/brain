import mido

import numpy as np
import threading
import time

from operator import itemgetter


import module


class Envgen:
    # Promote midi stream to audio rate CV, streaming over ethernet
    channels = 8
    updatefreq = 1000  # Hz
    atime = 0.05  # sec
    rtime = 0.25  # sec
    timestamp = 0

    voices = [
        {"note": 0, "on": False, "timestamp": 0, "env": 0, "envupdate": time.time()}
        for _ in range(channels)
    ]

    def __init__(self):
        print("Opening all midi inputs by default...")
        for inp in mido.get_input_names():
            mido.open_input(inp, callback=self.midi_to_cv_callback)

        self.module_interface = module.Module("Midi to CV converter")
        self.notedest = self.module_interface.add_output(
            {
                "id": 0,
                "name": "Note",
                "channels": self.channels,
                "samplerate": self.updatefreq,
                "format": "L16",
            }
        )
        self.gatedest = self.module_interface.add_output(
            {
                "id": 1,
                "name": "Gate",
                "channels": self.channels,
                "samplerate": self.updatefreq,
                "format": "L16",
            }
        )
        self.velodest = self.module_interface.add_output(
            {
                "id": 2,
                "name": "Velocity",
                "channels": self.channels,
                "samplerate": self.updatefreq,
                "format": "L16",
            }
        )
        self.liftdest = self.module_interface.add_output(
            {
                "id": 3,
                "name": "Lift",
                "channels": self.channels,
                "samplerate": self.updatefreq,
                "format": "L16",
            }
        )
        self.piwhdest = self.module_interface.add_output(
            {
                "id": 4,
                "name": "Pitch Wheel",
                "channels": 1,
                "samplerate": self.updatefreq,
                "format": "L16",
            }
        )
        self.mdwhdest = self.module_interface.add_output(
            {
                "id": 5,
                "name": "Mod Wheel",
                "channels": 1,
                "samplerate": self.updatefreq,
                "format": "L16",
            }
        )
        self.asredest = self.module_interface.add_output(
            {
                "id": 6,
                "name": "ASR Envelope",
                "channels": self.channels,
                "samplerate": self.updatefreq,
                "format": "L16",
            }
        )

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

            self.notedest.send(voct_data.tobytes())
            self.gatedest.send(gate_data.tobytes())
            self.asredest.send(level_data.tobytes())

            dtime = time.time() - currtime
            if dtime > (1 / self.updatefreq):
                continue
            else:
                time.sleep((1 / self.updatefreq) - dtime)


if __name__ == "__main__":
    e = Envgen()
    while True:
        time.sleep(1)
