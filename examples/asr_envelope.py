import asyncio
import numpy as np
import tkinter as tk
import time

from brain import module
from common import tkJack

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class ASREnvelope:
    atime = 1  # sec
    rtime = 2  # sec
    name = "ASR Envelope Generator"
    grid_size = (4, 10)
    grid_pos = (4, 0)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

        self.mod = module.Module(self.name, self.patching_callback)

        self.gate_jack = self.mod.add_input("Gate In", self.data_callback)
        self.asr_jack = self.mod.add_output("ASR Envelope")

        self.ui_setup()
        loop.create_task(self.ui_task())

        self.gates = [0] * self.mod.channels
        self.level = [0] * self.mod.channels

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

        tkJack(self.root, self.gate_jack, "Gate In").place(x=10, y=50)
        tkJack(self.root, self.asr_jack, "ASR Envelope").place(x=10, y=130)

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
            self.gates[i] = result[0, i]

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError:
                self.shutdown()
                break

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
        astep = 16000 / self.mod.packet_rate / self.atime
        rstep = 16000 / self.mod.packet_rate / self.rtime
        output = np.zeros((1, self.mod.channels), dtype=self.mod.sample_type)
        while True:
            dt = time.perf_counter() - t
            while dt > (1 / self.mod.packet_rate):
                for i, v in enumerate(self.gates):
                    if self.level[i] < v:
                        self.level[i] = min(v, self.level[i] + astep)
                    elif self.level[i] > v:
                        self.level[i] = max(v, self.level[i] - rstep)
                    output[0, i] = round(self.level[i])

                self.asr_jack.send(output.tobytes())
                t += 1 / self.mod.packet_rate
                dt = time.perf_counter() - t

            await asyncio.sleep(0)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = ASREnvelope(loop)
    loop.run_forever()
    loop.close()
