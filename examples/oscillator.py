import asyncio
import numpy as np
import tkinter as tk
import time

from brain import module

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class Oscillator:
    name = "Oscillator"
    grid_size = (4, 10)
    grid_pos = (8, 0)

    def __init__(self, loop):
        self.loop = loop

        self.ui_setup()
        loop.create_task(self.ui_task())

        self.mod = module.Module(self.name, self.patching_callback)

        self.notedest = self.mod.add_input("Note In", self.data_callback)
        self.outdest = self.mod.add_output(name="Output")

        self.note = [69 * 256] * self.mod.channels

        loop.create_task(self.output_task())

        self.mod.start()

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

    def data_callback(self, data):
        result = np.frombuffer(data, dtype=self.mod.sample_type)
        result = result.reshape((len(result) // self.mod.channels, self.mod.channels))
        for i in range(self.mod.channels):
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
        self.notedest.set_patch_enabled(self.cbnoteval.get())

    def out_check_handler(self):
        self.outdest.set_patch_enabled(self.cboutval.get())

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
        block_size = round(self.mod.sample_rate / self.mod.packet_rate)  # samples
        output = np.zeros((block_size, self.mod.channels), dtype=self.mod.sample_type)

        wavetable_size = 512  # samples
        wavetable = np.array(
            [
                round(8000 * np.sin(2 * np.pi * i / wavetable_size))
                for i in range(wavetable_size)
            ],
            dtype=self.mod.sample_type,
        )
        wavetable_pos = [0] * self.mod.channels

        while True:
            dt = time.perf_counter() - t
            while dt > (1 / self.mod.packet_rate):
                for i, v in enumerate(self.note):
                    f = 440 * 2 ** ((v / 256 - 69) / 12)
                    for j in range(block_size):
                        output[j, i] = wavetable[int(wavetable_pos[i])]
                        wavetable_pos[i] += f / self.mod.sample_rate * wavetable_size
                        if wavetable_pos[i] >= wavetable_size:
                            wavetable_pos[i] -= wavetable_size

                self.outdest.send(output.tobytes())
                t += 1 / self.mod.packet_rate
                dt = time.perf_counter() - t

            await asyncio.sleep(0)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Oscillator(loop)
    loop.run_forever()
    loop.close()
