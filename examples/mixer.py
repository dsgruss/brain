import asyncio
import numpy as np
import tkinter as tk

import brain
from common import tkJack, tkKnob

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class Mixer:

    name = "Mixer"
    color = 40  # hue
    inputs = 3

    grid_size = (4, 9)
    grid_pos = (12, 0)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

        self.mod = brain.Module(self.name, MixerEventHandler(self))

        self.in_jack = [self.mod.add_input(f"Input {i}") for i in range(self.inputs)]
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
        self.in_val = []
        for i in range(self.inputs):
            tkjack = tkJack(self.root, self.mod, self.in_jack[i], f"Input {i}")
            tkjack.place(x=10, y=(90 * i + 50))
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
            ).place(x=70, y=(75 + 90 * i))

        self.out_tkjack = tkJack(self.root, self.mod, self.out_jack, "Output")
        self.out_tkjack.place(x=10, y=375)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    def data_callback(self):
        output = np.zeros((brain.BLOCK_SIZE, brain.CHANNELS), dtype=brain.SAMPLE_TYPE)
        for i in range(self.inputs):
            output += (self.in_jack[i].get_data() * self.in_val[i].get()).astype(
                brain.SAMPLE_TYPE
            )
        self.out_jack.send(output.tobytes())

    async def module_task(self):
        while True:
            self.mod.update()
            await asyncio.sleep(1 / brain.PACKET_RATE)

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                for in_tkjack in self.in_tkjack:
                    in_tkjack.update_display(1.0)
                self.out_tkjack.update_display(1.0)

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
        for jack in self.in_tkjack:
            jack.patching_callback(state)
        self.out_tkjack.patching_callback(state)


class MixerEventHandler(brain.EventHandler):
    def __init__(self, app: Mixer) -> None:
        self.app = app

    def patch(self, state: brain.PatchState) -> None:
        self.app.patching_callback(state)

    def process(self) -> None:
        self.app.data_callback()

    def halt(self) -> None:
        self.app.shutdown()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Mixer(loop)
    loop.run_forever()
    loop.close()
