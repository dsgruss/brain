import asyncio
import numpy as np
import tkinter as tk
import time

from brain import module

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class ASREnvelope:
    channels = 8
    updatefreq = 1000  # Hz
    atime = 1  # sec
    rtime = 2  # sec
    name = "ASR Envelope Generator"
    grid_size = (4, 10)
    grid_pos = (4, 0)

    gates = [0] * channels
    level = [0] * channels

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
        self.gatedest = self.module_interface.add_input(
            self.data_callback, name="Gate In"
        )
        self.asredest = self.module_interface.add_output(name="ASR Envelope", **params)

        loop.create_task(self.output_task())

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 50
        y = self.grid_pos[1] * 50 + 50
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        self.cbgateval = tk.BooleanVar()
        self.cbasrval = tk.BooleanVar()

        self.cbgate = tk.Checkbutton(
            self.root,
            text="Gate In",
            variable=self.cbgateval,
            command=self.gate_check_handler,
        )
        self.cbgate.place(x=10, y=50)
        self.cbasr = tk.Checkbutton(
            self.root,
            text="ASR Envelope",
            variable=self.cbasrval,
            command=self.asr_check_handler,
        )
        self.cbasr.place(x=10, y=130)

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
            self.gates[i] = result[0, i]

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError:
                self.shutdown()
                break

    def gate_check_handler(self):
        self.gatedest.patch_enabled(self.cbgateval.get())

    def asr_check_handler(self):
        self.asredest.patch_enabled(self.cbasrval.get())

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
        astep = 16000 / self.updatefreq / self.atime
        rstep = 16000 / self.updatefreq / self.rtime
        output = np.zeros((1, self.channels), dtype=np.int16)
        while True:
            dt = time.perf_counter() - t
            while dt > (1 / self.updatefreq):
                for i, v in enumerate(self.gates):
                    if self.level[i] < v:
                        self.level[i] = min(v, self.level[i] + astep)
                    elif self.level[i] > v:
                        self.level[i] = max(v, self.level[i] - rstep)
                    output[0, i] = round(self.level[i])

                self.asredest.send(output.tobytes())
                t += 1 / self.updatefreq
                dt = time.perf_counter() - t

            await asyncio.sleep(0)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = ASREnvelope(loop)
    loop.run_forever()
    loop.close()
