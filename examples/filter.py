import asyncio
import numpy as np
import tkinter as tk

from scipy import signal

from brain import Module, EventHandler, PatchState
from common import tkJack

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class Filter:
    name = "Filter"
    color = 180  # hue

    grid_size = (4, 9)
    grid_pos = (12, 0)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

        self.mod = Module(self.name, FilterEventHandler(self))
        self.in_jack = self.mod.add_input("Audio In")
        self.out_jack = self.mod.add_output("Audio Out", color=self.color)

        self.filter_z = np.zeros((2, 2, 8))
        self.filter_val = 2

        self.ui_setup()
        loop.create_task(self.ui_task())

        self.mod.start()

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
        self.out_tkjack.place(x=10, y=170)

        self.slide_val = tk.DoubleVar()
        tk.Scale(
            self.root,
            variable=self.slide_val,
            from_=1,
            to=4,
            orient=tk.HORIZONTAL,
            resolution=0.001,
        ).place(x=10, y=100)
        self.slide_val.set(4)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    def data_callback(self):
        initial = self.mod.get_data(self.in_jack)
        self.filter_val += 0.025 * (self.slide_val.get() - self.filter_val)
        self.sos = signal.butter(
            4, 10 ** self.filter_val, "low", False, "sos", Module.sample_rate
        )
        result, self.filter_z = signal.sosfilt(
            self.sos, initial, axis=0, zi=self.filter_z
        )
        self.mod.send_data(self.out_jack, result.astype(Module.sample_type))

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                for jack in [self.in_tkjack, self.out_tkjack]:
                    jack.update_display(1)

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
        for jack in [self.in_tkjack, self.out_tkjack]:
            jack.patching_callback(state)


class FilterEventHandler(EventHandler):
    def __init__(self, app: Filter) -> None:
        self.app = app

    def patch(self, state: PatchState) -> None:
        self.app.patching_callback(state)

    def process(self) -> None:
        self.app.data_callback()

    def halt(self) -> None:
        self.app.shutdown()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Filter(loop)
    loop.run_forever()
    loop.close()
