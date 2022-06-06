import argparse
import asyncio
import numpy as np
import tkinter as tk

import pedalboard

import brain
from brain.constants import BLOCK_SIZE, CHANNELS, SAMPLE_RATE, SAMPLE_TYPE
from common import tkJack

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class Reverb(brain.EventHandler):

    name = "Reverb"

    grid_size = (4, 9)

    def __init__(self, loop: asyncio.AbstractEventLoop, args: argparse.Namespace):
        self.loop = loop
        self.grid_pos = (args.gridx, args.gridy)
        self.color = args.color

        self.mod = brain.Module(
            self.name,
            self,
            id="root:virtual_examples:reverb:" + str(args.id),
        )

        self.in_jack = self.mod.add_input("Audio In")
        self.out_jack = self.mod.add_output("Audio Out", self.color)

        self.reverbs = [pedalboard.Reverb() for _ in range(CHANNELS)]

        self.ui_setup()
        loop.create_task(self.ui_task())
        loop.create_task(self.module_task())

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50 - 10
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 10 + 5
        y = self.grid_pos[1] * 50 + 10
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        self.in_tkjack = tkJack(self.root, self.mod, self.in_jack, "Audio In")
        self.in_tkjack.place(x=10, y=50)

        self.out_tkjack = tkJack(self.root, self.mod, self.out_jack, "Audio Out")
        self.out_tkjack.place(x=10, y=200)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    def process(self, input: np.ndarray) -> np.ndarray:
        output = np.zeros((1, BLOCK_SIZE, CHANNELS))
        for i in range(CHANNELS):
            output[0, :, i] = self.reverbs[i](
                input[0, :, i],
                sample_rate=SAMPLE_RATE,
                buffer_size=BLOCK_SIZE,
                reset=False,
            )
        return output.astype(SAMPLE_TYPE)

    async def module_task(self):
        while True:
            self.mod.update()
            await asyncio.sleep(1 / brain.PACKET_RATE)

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.in_tkjack.update_display()
                self.out_tkjack.update_display()

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
        for jack in [self.in_tkjack, self.out_tkjack]:
            jack.patching_callback(state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reverb")
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
    app = Reverb(loop, args)
    loop.run_forever()
    loop.close()
