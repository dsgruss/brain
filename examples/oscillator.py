import argparse
import asyncio
import numpy as np
import tkinter as tk

import brain

import logging
from brain.constants import BLOCK_SIZE, CHANNELS, SAMPLE_TYPE, voct_to_frequency

from examples.common import tkJack, tkKnob

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class Oscillator(brain.EventHandler):
    name = "Oscillator"
    grid_size = (4, 9)

    def __init__(self, loop: asyncio.AbstractEventLoop, args: argparse.Namespace):
        self.loop = loop
        self.grid_pos = (args.gridx, args.gridy)
        self.color = args.color

        self.mod = brain.Module(
            self.name,
            self,
            id="root:virtual_examples:oscillator:" + str(args.id),
        )

        self.note_jack = self.mod.add_input("Note In")
        self.sin_jack = self.mod.add_output("Sin", self.color)
        self.tri_jack = self.mod.add_output("Tri", self.color)
        self.saw_jack = self.mod.add_output("Saw", self.color)
        self.sqr_jack = self.mod.add_output("Sqr", self.color)

        self.init_wavetables()

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

        self.note_tkjack = tkJack(self.root, self.mod, self.note_jack, "Note In")
        self.note_tkjack.place(x=10, y=50)
        self.sin_tkjack = tkJack(self.root, self.mod, self.sin_jack, "Sin")
        self.sin_tkjack.place(x=10, y=130)
        self.tri_tkjack = tkJack(self.root, self.mod, self.tri_jack, "Tri")
        self.tri_tkjack.place(x=10, y=170)
        self.saw_tkjack = tkJack(self.root, self.mod, self.saw_jack, "Saw")
        self.saw_tkjack.place(x=10, y=210)
        self.sqr_tkjack = tkJack(self.root, self.mod, self.sqr_jack, "Sqr")
        self.sqr_tkjack.place(x=10, y=250)

        self.fine_val = tk.DoubleVar()
        self.fine_val.set(0)
        tkKnob(
            self.root,
            "Fine Pitch",
            color=self.color,
            variable=self.fine_val,
            from_=-1,
            to=1,
        ).place(x=70, y=300)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                for jack in [
                    self.note_tkjack,
                    self.sin_tkjack,
                    self.tri_tkjack,
                    self.saw_tkjack,
                    self.sqr_tkjack,
                ]:
                    jack.update_display()
                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError:
                self.halt()
                break

    async def module_task(self):
        while True:
            self.mod.update()
            await asyncio.sleep(1 / brain.PACKET_RATE)

    def halt(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def quit(self):
        self.loop.stop()

    def patch(self, state):
        for jack in [
            self.note_tkjack,
            self.sin_tkjack,
            self.tri_tkjack,
            self.saw_tkjack,
            self.sqr_tkjack,
        ]:
            jack.patching_callback(state)

    def init_wavetables(self):

        self.wavetable_size = 2048  # samples
        wt_size = self.wavetable_size
        self.wavetable_pos = [0] * brain.CHANNELS

        a = 8000  # amplitude zero-to-peak
        self.sin_wavetable = np.array(
            [round(a * np.sin(2 * np.pi * i / wt_size)) for i in range(wt_size)],
            dtype=brain.SAMPLE_TYPE,
        )
        self.tri_wavetable = np.array(
            [round(-a + 2 * a * i / (wt_size // 2)) for i in range(wt_size // 2)]
            + [
                round(a - 2 * a * (i - wt_size // 2) / (wt_size // 2))
                for i in range(wt_size // 2, wt_size)
            ],
            dtype=brain.SAMPLE_TYPE,
        )
        self.saw_wavetable = np.array(
            [round(-a + 2 * a * i / wt_size) for i in range(wt_size)],
            dtype=brain.SAMPLE_TYPE,
        )
        self.sqr_wavetable = np.array(
            [a if i < wt_size // 2 else -a for i in range(wt_size)],
            dtype=brain.SAMPLE_TYPE,
        )

    def process(self, input):
        output = np.zeros((4, BLOCK_SIZE, CHANNELS), dtype=SAMPLE_TYPE)

        for i, v in enumerate(input[0, 0, :]):
            f = voct_to_frequency(v + 512 * self.fine_val.get())
            for j in range(brain.BLOCK_SIZE):
                output[0, j, i] = self.sin_wavetable[int(self.wavetable_pos[i])]
                output[1, j, i] = self.tri_wavetable[int(self.wavetable_pos[i])]
                output[2, j, i] = self.saw_wavetable[int(self.wavetable_pos[i])]
                output[3, j, i] = self.sqr_wavetable[int(self.wavetable_pos[i])]
                self.wavetable_pos[i] += f / brain.SAMPLE_RATE * self.wavetable_size
                if self.wavetable_pos[i] >= self.wavetable_size:
                    self.wavetable_pos[i] -= self.wavetable_size

        return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Oscillator")
    parser.add_argument(
        "--gridx", default=8, type=int, help="Window X position in the grid"
    )
    parser.add_argument(
        "--gridy", default=0, type=int, help="Window Y position in the grid"
    )
    parser.add_argument(
        "--color", default=120, type=int, help="HSV Hue color of the interface"
    )
    parser.add_argument("--id", default=0, type=int, help="Unique identifier postfix")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    app = Oscillator(loop, args)
    loop.run_forever()
    loop.close()
