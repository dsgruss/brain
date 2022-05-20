import asyncio
import numpy as np
import tkinter as tk
import time

from brain import module

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class Oscillator:
    channels = 8
    updatefreq = 1000  # Hz
    name = "Oscillator"
    grid_size = (4, 10)
    grid_pos = (8, 0)

    note = [69 * 256] * channels

    def __init__(self, loop):
        self.loop = loop

        self.ui_setup()
        loop.create_task(self.ui_task())

        self.module_interface = module.Module(self.name, self.patching_callback)
        params = {
            "channels": self.channels,
            "sample_rate": self.updatefreq,
            "format": "L16",
        }
        self.notedest = self.module_interface.add_input(
            self.data_callback, name="Note In"
        )
        self.outdest = self.module_interface.add_output(name="Output", **params)

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
        self.cboutval = tk.BooleanVar()

        self.cbnote = tk.Checkbutton(
            self.root,
            text="Note In",
            variable=self.cbnoteval,
            command=self.note_check_handler,
        )
        self.cbnote.place(x=10, y=50)
        self.cbout = tk.Checkbutton(
            self.root,
            text="Output",
            variable=self.cboutval,
            command=self.out_check_handler,
        )
        self.cbout.place(x=10, y=130)

        tk.Label(self.root, text=self.name).place(x=10, y=10)
        tk.Button(self.root, text="Quit", command=self.shutdown).place(x=10, y=170)

        self.statusbar = tk.Label(
            self.root, text="Loading...", bd=1, relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    def data_callback(self, data, sample_rate):
        result = np.frombuffer(data, dtype=np.int16)
        result = result.reshape((len(result) // self.channels, self.channels))
        for i in range(self.channels):
            self.note[i] = result[0, i]

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError:
                self.shutdown()
                break

    def note_check_handler(self):
        self.notedest.patch_enabled(self.cbgateval.get())

    def out_check_handler(self):
        self.outdest.patch_enabled(self.cbasrval.get())

    def shutdown(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def quit(self):
        self.loop.stop()

    def patching_callback(self, state):
        self.statusbar.config(text=str(state))

    async def output_task(self):
        t = time.perf_counter()
        window_size = 48  # samples
        output = np.zeros((window_size, self.channels), dtype=np.int16)

        wavetable_size = 512  # samples
        wavetable = np.array(
            [
                round(8000 * np.sin(2 * np.pi * i / wavetable_size))
                for i in range(wavetable_size)
            ],
            dtype=np.int16,
        )
        wavetable_pos = [0] * self.channels

        while True:
            dt = time.perf_counter() - t
            while dt > (1 / self.updatefreq):
                for i, v in enumerate(self.note):
                    f = 440 * 2 ** ((v / 256 - 69) / 12)
                    for j in range(window_size):
                        output[j, i] = wavetable[int(wavetable_pos[i])]
                        wavetable_pos[i] += (
                            f / self.updatefreq * wavetable_size / window_size
                        )
                        if wavetable_pos[i] >= wavetable_size:
                            wavetable_pos[i] -= wavetable_size

                self.outdest.send(output.tobytes())
                t += 1 / self.updatefreq
                dt = time.perf_counter() - t

            await asyncio.sleep(0)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Oscillator(loop)
    loop.run_forever()
    loop.close()
