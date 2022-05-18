import mido
import numpy as np
import threading
import time
import tkinter

from operator import itemgetter
from tkinter import ttk

from brain import module


class Envgen:
    # Promote midi stream to control voltages
    channels = 8
    updatefreq = 1000  # Hz
    atime = 0.05  # sec
    rtime = 0.25  # sec
    timestamp = 0
    running = True
    name = "Midi to CV converter"

    voices = [
        {"note": 0, "on": False, "timestamp": 0, "env": 0, "envupdate": time.time()}
        for _ in range(channels)
    ]

    def __init__(self):

        self.module_interface = module.Module(self.name)
        params = {
            "channels": self.channels,
            "samplerate": self.updatefreq,
            "format": "L16",
        }
        self.notedest = self.module_interface.add_output(name="Note", **params)
        self.gatedest = self.module_interface.add_output(name="Gate", **params)
        self.velodest = self.module_interface.add_output(name="Velocity", **params)
        self.liftdest = self.module_interface.add_output(name="Lift", **params)
        self.piwhdest = self.module_interface.add_output(name="Pitch Wheel", **params)
        self.mdwhdest = self.module_interface.add_output(name="Mod Wheel", **params)
        self.asredest = self.module_interface.add_output(name="ASR Envelope", **params)

        threading.Thread(target=self.output_thread, daemon=True).start()
        threading.Thread(target=self.ui_thread, daemon=True).start()

        # print("Opening all midi inputs by default...")
        # for inp in mido.get_input_names():
        #     mido.open_input(inp, callback=self.midi_to_cv_callback)

    def ui_thread(self):
        root = tkinter.Tk()
        root.geometry("200x500")

        self.cbnoteval = tkinter.BooleanVar()
        self.cbgateval = tkinter.BooleanVar()
        self.cbasrval = tkinter.BooleanVar()

        self.cbnote = ttk.Checkbutton(
            root, text="Note", variable=self.cbnoteval, command=self.note_check_handler
        )
        self.cbnote.place(x=10, y=50)
        self.cbgate = ttk.Checkbutton(
            root, text="Gate", variable=self.cbgateval, command=self.gate_check_handler
        )
        self.cbgate.place(x=10, y=90)
        self.cbasr = ttk.Checkbutton(
            root,
            text="ASR Envelope",
            variable=self.cbasrval,
            command=self.asr_check_handler,
        )
        self.cbasr.place(x=10, y=130)

        ttk.Label(root, text=self.name).place(x=10, y=10)
        ttk.Button(root, text="Quit", command=self.shutdown).place(x=10, y=170)

        root.mainloop()
        self.shutdown()

    def note_check_handler(self):
        self.notedest.patch_enabled(self.cbnoteval.get())

    def gate_check_handler(self):
        self.gatedest.patch_enabled(self.cbgateval.get())

    def asr_check_handler(self):
        self.asredest.patch_enabled(self.cbasrval.get())

    def check_handler(self):
        if self.cbnoteval.get():
            self.cbgate["state"] = tkinter.DISABLED
            self.cbasr["state"] = tkinter.DISABLED
        elif self.cbgateval.get():
            self.cbnote["state"] = tkinter.DISABLED
            self.cbasr["state"] = tkinter.DISABLED
        elif self.cbasrval.get():
            self.cbnote["state"] = tkinter.DISABLED
            self.cbgate["state"] = tkinter.DISABLED
        else:
            self.cbnote["state"] = tkinter.NORMAL
            self.cbgate["state"] = tkinter.NORMAL
            self.cbasr["state"] = tkinter.NORMAL

    def shutdown(self):
        self.running = False

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
    while e.running:
        time.sleep(1)
