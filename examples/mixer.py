import argparse
import asyncio
from itertools import chain
import numpy as np
import tkinter as tk

import brain
from common import tkJack, tkKnob

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class Mixer(brain.EventHandler):
    name = "Mixer"
    inputs = 3
    grid_size = (4, 9)

    def __init__(self, loop: asyncio.AbstractEventLoop, args: argparse.Namespace):
        self.loop = loop
        self.grid_pos = (args.gridx, args.gridy)
        self.color = args.color

        self.mod = brain.Module(
            self.name,
            self,
            id="root:virtual_examples:mixer:" + str(args.id),
        )

        self.in_jack = [self.mod.add_input(f"Input {i}") for i in range(self.inputs)]
        self.cv_jack = [self.mod.add_input(f"CV {i}") for i in range(self.inputs)]
        self.out_jack = self.mod.add_output("Output", self.color)

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

        self.in_tkjack = []
        self.cv_tkjack = []
        self.in_val = []
        for i in range(self.inputs):
            tkjack = tkJack(self.root, self.mod, self.in_jack[i], f"Input {i}")
            tkjack.place(x=10, y=(90 * i + 50))
            self.in_tkjack.append(tkjack)

            tkjack = tkJack(self.root, self.mod, self.cv_jack[i], f"CV {i}")
            tkjack.place(x=10, y=(90 * i + 80))
            self.in_tkjack.append(tkjack)

            in_val = tk.DoubleVar()
            in_val.set(0.25)
            self.in_val.append(in_val)
            tkKnob(
                self.root,
                f"Level {i}",
                color=self.color,
                variable=in_val,
                from_=0.0,
                to=1.0,
            ).place(x=125, y=(50 + 90 * i))

        self.out_tkjack = tkJack(self.root, self.mod, self.out_jack, "Output")
        self.out_tkjack.place(x=10, y=375)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    def process(self, input):
        output = np.zeros((1, brain.BLOCK_SIZE, brain.CHANNELS))
        for i in range(self.inputs):
            if self.mod.is_patched(self.cv_jack[i]):
                output[0] += (
                    input[i] * (input[i + self.inputs] / 16000)
                ) * self.in_val[i].get()
            else:
                output[0] += input[i] * self.in_val[i].get()
        return output.astype(brain.SAMPLE_TYPE)

    async def module_task(self):
        while True:
            self.mod.update()
            await asyncio.sleep(1 / brain.PACKET_RATE)

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                for in_tkjack in self.in_tkjack:
                    in_tkjack.update_display()
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
        for jack in chain(self.in_tkjack, self.cv_tkjack):
            jack.patching_callback(state)
        self.out_tkjack.patching_callback(state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mixer")
    parser.add_argument(
        "--gridx", default=12, type=int, help="Window X position in the grid"
    )
    parser.add_argument(
        "--gridy", default=0, type=int, help="Window Y position in the grid"
    )
    parser.add_argument(
        "--color", default=40, type=int, help="HSV Hue color of the interface"
    )
    parser.add_argument("--id", default=0, type=int, help="Unique identifier postfix")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    app = Mixer(loop, args)
    loop.run_forever()
    loop.close()
