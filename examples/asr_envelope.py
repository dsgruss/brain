import asyncio
import numpy as np
import tkinter as tk
import time

import brain
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

        self.mod = brain.Module(self.name, ASREnvelopeEventHandler(self))

        self.gate_jack = self.mod.add_input("Gate In")
        self.asr_jack = self.mod.add_output("ASR Envelope", self.color)

        self.ui_setup()
        loop.create_task(self.ui_task())

        self.gates = [0] * brain.CHANNELS
        self.level = [0] * brain.CHANNELS

        loop.create_task(self.output_task())
        loop.create_task(self.module_task())

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

    def data_callback(self):
        data = self.gate_jack.get_data()
        for i in range(brain.CHANNELS):
            self.gates[i] = data[0, i]

    async def module_task(self):
        while True:
            self.mod.update()
            await asyncio.sleep(1 / brain.PACKET_RATE)

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
        astep = 16000 / brain.PACKET_RATE / self.atime
        rstep = 16000 / brain.PACKET_RATE / self.rtime
        output = np.zeros((1, brain.CHANNELS), dtype=brain.SAMPLE_TYPE)
        while True:
            dt = time.perf_counter() - t
            while dt > (1 / brain.PACKET_RATE):
                for i, v in enumerate(self.gates):
                    if self.level[i] < v:
                        self.level[i] = min(v, self.level[i] + astep)
                    elif self.level[i] > v:
                        self.level[i] = max(v, self.level[i] - rstep)
                    output[0, i] = round(self.level[i])

                self.mod.send_data(self.asr_jack, output)
                t += 1 / brain.PACKET_RATE
                dt = time.perf_counter() - t

            await asyncio.sleep(1 / brain.PACKET_RATE)


class ASREnvelopeEventHandler(brain.EventHandler):
    def __init__(self, app: ASREnvelope) -> None:
        self.app = app

    def patch(self, state: brain.PatchState) -> None:
        self.app.patching_callback(state)

    def process(self) -> None:
        self.app.data_callback()

    def halt(self) -> None:
        self.app.shutdown()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = ASREnvelope(loop)
    loop.run_forever()
    loop.close()
