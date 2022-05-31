import asyncio
import numpy as np
import tkinter as tk

from scipy import signal

import brain
from brain.constants import BLOCK_SIZE, CHANNELS, SAMPLE_RATE
from common import tkJack, tkKnob

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class Filter:
    name = "Filter"
    color = 180  # hue

    grid_size = (4, 9)
    grid_pos = (16, 0)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

        self.mod = brain.Module(self.name, FilterEventHandler(self), use_block_callback=True)
        self.in_jack = self.mod.add_input("Audio In")
        self.key_jack = self.mod.add_input("Key Track")
        self.out_jack = self.mod.add_output("Audio Out", color=self.color)

        self.filter_z = np.zeros((2, 2, 8))
        self.filter_val = 2

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
        tk.Label(self.root, text=self.name).place(x=10, y=10)

        self.in_tkjack = tkJack(self.root, self.mod, self.in_jack, "Audio In")
        self.in_tkjack.place(x=10, y=50)
        self.key_tkjack = tkJack(self.root, self.mod, self.key_jack, "Key Track")
        self.key_tkjack.place(x=10, y=80)

        self.cutoff_val = tk.DoubleVar()
        self.cutoff_val.set(1000)
        tkKnob(
            self.root,
            "Cutoff",
            color=self.color,
            variable=self.cutoff_val,
            from_=20,
            to=20000,
            log=True,
        ).place(x=70, y=140)

        self.out_tkjack = tkJack(self.root, self.mod, self.out_jack, "Audio Out")
        self.out_tkjack.place(x=10, y=250)

    def data_callback(self, input):
        result = np.zeros((1, BLOCK_SIZE, CHANNELS))
        self.sos = signal.butter(
            4, self.cutoff_val.get(), "low", False, "sos", brain.SAMPLE_RATE
        )
        result[0, :, :], self.filter_z = signal.sosfilt(
            self.sos, input[0, :, :], axis=0, zi=self.filter_z
        )
        return result.astype(brain.SAMPLE_TYPE)

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                for jack in [self.in_tkjack, self.key_tkjack, self.out_tkjack]:
                    jack.update_display(1.0)

                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError:
                self.shutdown()
                break

    async def module_task(self):
        while True:
            self.mod.update()
            await asyncio.sleep(1 / brain.PACKET_RATE)

    def shutdown(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def quit(self):
        self.loop.stop()

    def patching_callback(self, state):
        for jack in [self.in_tkjack, self.out_tkjack]:
            jack.patching_callback(state)


class FilterEventHandler(brain.EventHandler):
    def __init__(self, app: Filter) -> None:
        self.app = app

    def patch(self, state: brain.PatchState) -> None:
        self.app.patching_callback(state)

    def block_process(self, input: np.ndarray) -> np.ndarray:
        return self.app.data_callback(input)

    def halt(self) -> None:
        self.app.shutdown()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Filter(loop)
    loop.run_forever()
    loop.close()
