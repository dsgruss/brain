import asyncio
import numpy as np
import tkinter as tk
import time

from brain import Module, PatchState

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

        self.mod = Module(
            self.name, self.patching_callback, abort_callback=self.shutdown
        )

        self.note_jack = self.mod.add_input("Note In", self.data_callback)
        self.sin_jack = self.mod.add_output("Sin", self.color)
        self.tri_jack = self.mod.add_output("Tri", self.color)
        self.saw_jack = self.mod.add_output("Saw", self.color)
        self.sqr_jack = self.mod.add_output("Sqr", self.color)

        self.note = [69 * 256] * Module.channels

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
        self.sin_tkjack = tkJack(self.root, self.sin_jack, "Sin")
        self.sin_tkjack.place(x=10, y=130)
        self.tri_tkjack = tkJack(self.root, self.tri_jack, "Tri")
        self.tri_tkjack.place(x=10, y=170)
        self.saw_tkjack = tkJack(self.root, self.saw_jack, "Saw")
        self.saw_tkjack.place(x=10, y=210)
        self.sqr_tkjack = tkJack(self.root, self.sqr_jack, "Sqr")
        self.sqr_tkjack.place(x=10, y=250)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    def data_callback(self, data):
        result = np.frombuffer(data, dtype=Module.sample_type)
        result = result.reshape((len(result) // Module.channels, Module.channels))
        for i in range(Module.channels):
            self.note[i] = result[0, i]

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
        for jack in [
            self.note_tkjack,
            self.sin_tkjack,
            self.tri_tkjack,
            self.saw_tkjack,
            self.sqr_tkjack,
        ]:
            jack.patching_callback(state)

    async def output_task(self):
        t = time.perf_counter()
        sin_output = np.zeros(
            (Module.block_size, Module.channels), dtype=Module.sample_type
        )
        tri_output = np.zeros(
            (Module.block_size, Module.channels), dtype=Module.sample_type
        )
        saw_output = np.zeros(
            (Module.block_size, Module.channels), dtype=Module.sample_type
        )
        sqr_output = np.zeros(
            (Module.block_size, Module.channels), dtype=Module.sample_type
        )

        wavetable_size = 2048  # samples
        wavetable_pos = [0] * Module.channels

        a = 8000  # amplitude zero-to-peak
        sin_wavetable = np.array(
            [
                round(a * np.sin(2 * np.pi * i / wavetable_size))
                for i in range(wavetable_size)
            ],
            dtype=Module.sample_type,
        )
        tri_wavetable = np.array(
            [
                round(-a + 2 * a * i / (wavetable_size // 2))
                for i in range(wavetable_size // 2)
            ]
            + [
                round(a - 2 * a * (i - wavetable_size // 2) / (wavetable_size // 2))
                for i in range(wavetable_size // 2, wavetable_size)
            ],
            dtype=Module.sample_type,
        )
        saw_wavetable = np.array(
            [round(-a + 2 * a * i / wavetable_size) for i in range(wavetable_size)],
            dtype=Module.sample_type,
        )
        sqr_wavetable = np.array(
            [a if i < wavetable_size // 2 else -a for i in range(wavetable_size)],
            dtype=Module.sample_type,
        )

        while True:
            dt = time.perf_counter() - t
            while dt > (1 / Module.packet_rate):
                for i, v in enumerate(self.note):
                    f = 440 * 2 ** ((v / 256 - 69) / 12)
                    for j in range(Module.block_size):
                        sin_output[j, i] = sin_wavetable[int(wavetable_pos[i])]
                        tri_output[j, i] = tri_wavetable[int(wavetable_pos[i])]
                        saw_output[j, i] = saw_wavetable[int(wavetable_pos[i])]
                        sqr_output[j, i] = sqr_wavetable[int(wavetable_pos[i])]
                        wavetable_pos[i] += f / Module.sample_rate * wavetable_size
                        if wavetable_pos[i] >= wavetable_size:
                            wavetable_pos[i] -= wavetable_size

                self.sin_jack.send(sin_output.tobytes())
                self.tri_jack.send(tri_output.tobytes())
                self.saw_jack.send(saw_output.tobytes())
                self.sqr_jack.send(sqr_output.tobytes())
                t += 1 / Module.packet_rate
                dt = time.perf_counter() - t

            await asyncio.sleep(0)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Oscillator(loop)
    loop.run_forever()
    loop.close()
