import argparse
import asyncio
import numpy as np
import tkinter as tk

import brain
from common import tkJack, tkKnob

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class ASREnvelope(brain.EventHandler):

    name = "ASR Envelope Generator"

    grid_size = (4, 9)

    def __init__(self, loop: asyncio.AbstractEventLoop, args: argparse.Namespace):
        self.loop = loop
        self.grid_pos = (args.gridx, args.gridy)
        self.color = args.color

        self.mod = brain.Module(
            self.name,
            self,
            id="root:virtual_examples:asr_envelope:" + str(args.id),
        )

        self.gate_jack = self.mod.add_input("Gate In")
        self.asr_jack = self.mod.add_output("ASR Envelope", self.color)

        self.ui_setup()
        loop.create_task(self.ui_task())

        self.level = [0] * brain.CHANNELS

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

        self.attack_val = tk.DoubleVar()
        self.attack_val.set(0.25)
        tkKnob(
            self.root,
            "Attack",
            color=self.color,
            variable=self.attack_val,
            from_=0.001,
            to=25.0,
            log=True,
        ).place(x=35, y=100)

        self.release_val = tk.DoubleVar()
        self.release_val.set(2)
        tkKnob(
            self.root,
            "Release",
            color=self.color,
            variable=self.release_val,
            from_=0.001,
            to=25.0,
            log=True,
        ).place(x=105, y=100)

        self.asr_tkjack = tkJack(self.root, self.mod, self.asr_jack, "ASR Envelope")
        self.asr_tkjack.place(x=10, y=200)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    async def module_task(self):
        while True:
            self.mod.update()
            await asyncio.sleep(1 / brain.PACKET_RATE)

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.gate_tkjack.update_display()
                self.asr_tkjack.update_display()

                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError:
                self.halt()
                break

    def halt(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def quit(self):
        self.loop.stop()

    def patch(self, state):
        for jack in [self.gate_tkjack, self.asr_tkjack]:
            jack.patching_callback(state)

    def process(self, input):

        output = np.zeros((1, brain.BLOCK_SIZE, brain.CHANNELS))

        atime = self.attack_val.get()
        rtime = self.release_val.get()
        astep = 16000 / brain.PACKET_RATE / atime
        rstep = 16000 / brain.PACKET_RATE / rtime
        for i, v in enumerate(input[0, 0, :]):
            if self.level[i] < v:
                output[0, :, i] = np.linspace(
                    self.level[i], self.level[i] + astep, brain.BLOCK_SIZE
                ).clip(max=v)
                self.level[i] = min(v, self.level[i] + astep)
            else:
                output[0, :, i] = np.linspace(
                    self.level[i], self.level[i] - rstep, brain.BLOCK_SIZE
                ).clip(min=v)
                self.level[i] = max(v, self.level[i] - rstep)

        return output.astype(brain.SAMPLE_TYPE)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ASR Envelope Generator")
    parser.add_argument(
        "--gridx", default=4, type=int, help="Window X position in the grid"
    )
    parser.add_argument(
        "--gridy", default=0, type=int, help="Window Y position in the grid"
    )
    parser.add_argument(
        "--color", default=235, type=int, help="HSV Hue color of the interface"
    )
    parser.add_argument("--id", default=0, type=int, help="Unique identifier postfix")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    app = ASREnvelope(loop, args)
    loop.run_forever()
    loop.close()
