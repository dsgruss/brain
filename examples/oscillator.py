import asyncio
import numpy as np
import tkinter as tk
import time

from brain import module

import logging

from examples.common import tkJack

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class Oscillator:
    name = "Oscillator"
    color = 120  # hue

    grid_size = (4, 9)
    grid_pos = (8, 0)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

        self.mod = module.Module(
            self.name, self.patching_callback, abort_callback=self.shutdown
        )

        self.note_jack = self.mod.add_input("Note In", self.data_callback)
        self.out_jack = self.mod.add_output("Output", self.color)

        self.note = [69 * 256] * self.mod.channels

        self.ui_setup()
        loop.create_task(self.ui_task())

        loop.create_task(self.output_task())

        self.mod.start()

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50 - 10
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 10 + 5
        y = self.grid_pos[1] * 50 + 10
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        self.note_tkjack = tkJack(self.root, self.note_jack, "Note In")
        self.note_tkjack.place(x=10, y=50)
        self.out_tkjack = tkJack(self.root, self.out_jack, "Output")
        self.out_tkjack.place(x=10, y=130)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    def data_callback(self, data):
        result = np.frombuffer(data, dtype=self.mod.sample_type)
        result = result.reshape((len(result) // self.mod.channels, self.mod.channels))
        for i in range(self.mod.channels):
            self.note[i] = result[0, i]

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                if self.mod.patch_state == module.PatchState.IDLE:
                    self.out_tkjack.set_color(self.color, 100, 100)
                    if self.note_jack.is_patched():
                        self.note_tkjack.set_color(self.note_jack.color, 100, 100)
                    else:
                        self.note_tkjack.set_color(0, 0, 0)
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
        for jack in [self.note_tkjack, self.out_tkjack]:
            if state == module.PatchState.PATCH_TOGGLED:
                jack.set_color(77, 100, 100)
            elif state == module.PatchState.PATCH_ENABLED:
                jack.set_color(0, 0, 50)
            elif state == module.PatchState.BLOCKED:
                jack.set_color(0, 100, 100)

    async def output_task(self):
        t = time.perf_counter()
        block_size = round(self.mod.sample_rate / self.mod.packet_rate)  # samples
        output = np.zeros((block_size, self.mod.channels), dtype=self.mod.sample_type)

        wavetable_size = 2048  # samples
        wavetable = np.array(
            [
                round(8000 * np.sin(2 * np.pi * i / wavetable_size))
                for i in range(wavetable_size)
            ],
            dtype=self.mod.sample_type,
        )
        wavetable_pos = [0] * self.mod.channels

        while True:
            dt = time.perf_counter() - t
            while dt > (1 / self.mod.packet_rate):
                for i, v in enumerate(self.note):
                    f = 440 * 2 ** ((v / 256 - 69) / 12)
                    for j in range(block_size):
                        output[j, i] = wavetable[int(wavetable_pos[i])]
                        wavetable_pos[i] += f / self.mod.sample_rate * wavetable_size
                        if wavetable_pos[i] >= wavetable_size:
                            wavetable_pos[i] -= wavetable_size

                self.out_jack.send(output.tobytes())
                t += 1 / self.mod.packet_rate
                dt = time.perf_counter() - t

            await asyncio.sleep(0)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Oscillator(loop)
    loop.run_forever()
    loop.close()
