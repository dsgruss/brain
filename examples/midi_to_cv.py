import asyncio
import mido
import numpy as np
import time
import tkinter as tk

from operator import itemgetter

from brain import module

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class MidiToCV:
    # Promote midi stream to control voltages
    channels = 8
    updatefreq = 1000  # Hz
    timestamp = 0
    name = "Midi to CV converter"
    grid_size = (4, 10)
    grid_pos = (0, 0)

    voices = [{"note": 0, "on": False, "timestamp": 0} for _ in range(channels)]

    def __init__(self, loop):
        self.loop = loop

        self.ui_setup()
        loop.create_task(self.ui_task())

        logging.info("Opening all midi inputs by default...")
        for inp in mido.get_input_names():
            loop.create_task(self.midi_task(mido.open_input(inp)))

        self.module_interface = module.Module(self.name, self.patching_callback)
        params = {
            "channels": self.channels,
            "sample_rate": self.updatefreq,
            "format": "L16",
        }
        self.notedest = self.module_interface.add_output(name="Note", **params)
        self.gatedest = self.module_interface.add_output(name="Gate", **params)
        self.velodest = self.module_interface.add_output(name="Velocity", **params)
        self.liftdest = self.module_interface.add_output(name="Lift", **params)
        self.piwhdest = self.module_interface.add_output(name="Pitch Wheel", **params)
        self.mdwhdest = self.module_interface.add_output(name="Mod Wheel", **params)

        loop.create_task(self.output_task())

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 50
        y = self.grid_pos[1] * 50 + 50
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        self.cbnoteval = tk.BooleanVar()
        self.cbgateval = tk.BooleanVar()
        self.cbasrval = tk.BooleanVar()

        self.cbnote = tk.Checkbutton(
            self.root,
            text="Note",
            variable=self.cbnoteval,
            command=self.note_check_handler,
        )
        self.cbnote.place(x=10, y=50)
        self.cbgate = tk.Checkbutton(
            self.root,
            text="Gate",
            variable=self.cbgateval,
            command=self.gate_check_handler,
        )
        self.cbgate.place(x=10, y=90)

        tk.Label(self.root, text=self.name).place(x=10, y=10)
        tk.Button(self.root, text="Quit", command=self.shutdown).place(x=10, y=170)

        self.statusbar = tk.Label(
            self.root, text="Loading...", bd=1, relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError:
                self.shutdown()
                break

    def note_check_handler(self):
        self.notedest.patch_enabled(self.cbnoteval.get())

    def gate_check_handler(self):
        self.gatedest.patch_enabled(self.cbgateval.get())

    def shutdown(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def quit(self):
        self.loop.stop()

    def patching_callback(self, state):
        self.statusbar.config(text=str(state))

    async def midi_task(self, port, interval=1 / 60):
        while True:
            for message in port.iter_pending():
                logging.info(message)
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
                        voice_steal = min(self.voices, key=itemgetter("timestamp"))
                        voice_steal["note"] = message.note
                        voice_steal["timestamp"] = self.timestamp
                logging.info("\n\t".join([str(v) for v in self.voices]))
            await asyncio.sleep(interval)

    async def output_task(self):
        """Send the data as CV over over all requested ports and addresses at the configured sample
        rate"""

        t = time.perf_counter()
        voct_data = np.zeros((1, 8), dtype=np.int16)
        gate_data = np.zeros((1, 8), dtype=np.int16)
        while True:
            dt = time.perf_counter() - t
            while dt > (1 / self.updatefreq):
                for i, v in enumerate(self.voices):
                    voct_data[0, i] = v["note"] * 256
                    gate_data[0, i] = 16000 if v["on"] else 0

                self.notedest.send(voct_data.tobytes())
                self.gatedest.send(gate_data.tobytes())
                t += 1 / self.updatefreq
                dt = time.perf_counter() - t

            await asyncio.sleep(0)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = MidiToCV(loop)
    loop.run_forever()
    loop.close()
