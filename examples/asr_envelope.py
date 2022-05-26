import asyncio
import numpy as np
import tkinter as tk
import time

from brain import Module, EventHandler, PatchState
from common import tkJack

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class ASREnvelope:
    atime = 0.25  # sec
    rtime = 2  # sec

    name = "ASR Envelope Generator"
    color = 235  # hue

    grid_size = (4, 9)
    grid_pos = (4, 0)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

        self.mod = Module(self.name, ASREnvelopeEventHandler(self))

        self.gate_jack = self.mod.add_input("Gate In", self.data_callback)
        self.asr_jack = self.mod.add_output("ASR Envelope", self.color)

        self.ui_setup()
        loop.create_task(self.ui_task())

        self.gates = [0] * Module.channels
        self.level = [0] * Module.channels

        loop.create_task(self.output_task())

        loop.run_until_complete(self.mod.start())

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50 - 10
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 10 + 5
        y = self.grid_pos[1] * 50 + 10
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        self.gate_tkjack = tkJack(self.root, self.mod, self.gate_jack, "Gate In")
        self.gate_tkjack.place(x=10, y=50)
        self.asr_tkjack = tkJack(self.root, self.mod, self.asr_jack, "ASR Envelope")
        self.asr_tkjack.place(x=10, y=130)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    def data_callback(self, data):
        result = np.frombuffer(data, dtype=Module.sample_type)
        result = result.reshape((len(result) // Module.channels, Module.channels))
        for i in range(Module.channels):
            self.gates[i] = result[0, i]

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.gate_tkjack.update_display(max(self.gates) / 16000)
                self.asr_tkjack.update_display(max(self.level) / 16000)

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
        for jack in [self.gate_tkjack, self.asr_tkjack]:
            jack.patching_callback(state)

    async def output_task(self):
        t = time.perf_counter()
        astep = 16000 / Module.packet_rate / self.atime
        rstep = 16000 / Module.packet_rate / self.rtime
        output = np.zeros((1, Module.channels), dtype=Module.sample_type)
        while True:
            dt = time.perf_counter() - t
            while dt > (1 / Module.packet_rate):
                for i, v in enumerate(self.gates):
                    if self.level[i] < v:
                        self.level[i] = min(v, self.level[i] + astep)
                    elif self.level[i] > v:
                        self.level[i] = max(v, self.level[i] - rstep)
                    output[0, i] = round(self.level[i])

                self.mod.send_data(self.asr_jack, output)
                t += 1 / Module.packet_rate
                dt = time.perf_counter() - t

            await asyncio.sleep(1 / Module.packet_rate)


class ASREnvelopeEventHandler(EventHandler):
    def __init__(self, app: ASREnvelope) -> None:
        self.app = app

    def patch(self, state: PatchState) -> None:
        self.app.patching_callback(state)

    def halt(self) -> None:
        self.app.shutdown()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = ASREnvelope(loop)
    loop.run_forever()
    loop.close()
