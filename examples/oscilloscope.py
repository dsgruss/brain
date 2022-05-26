import asyncio
import matplotlib
import numpy as np
import random
import tkinter as tk
import time

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.lines import Line2D

from brain import Module, EventHandler, PatchState
from common import tkJack

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
matplotlib.use("TkAgg")


class Oscilloscope:
    name = "Oscilloscope"
    time_div = 4.0  # sec
    grid_size = (8, 9)
    grid_pos = (20, 0)

    def __init__(self, loop):
        self.loop = loop

        self.mod = Module(self.name, OscilloscopeEventHandler(self))
        self.data_jack = self.mod.add_input("Data", self.data_callback)

        self.ui_setup()
        loop.create_task(self.ui_task())

        self.dataseries = [[] for _ in range(Module.channels)]
        self.timeseries = [[] for _ in range(Module.channels)]

        # loop.create_task(self.random_square_wave())
        # loop.create_task(self.sin_wave())
        # loop.create_task(self.triangle_wave())

        loop.create_task(self.module_task())

    def data_callback(self, data):
        result = np.frombuffer(data, dtype=Module.sample_type)
        if len(self.timeseries[0]) == 0:
            t = 0
        else:
            t = self.timeseries[0][-1] + (1 / Module.packet_rate)
        for i in range(Module.channels):
            self.dataseries[i].append(result[i])
            self.timeseries[i].append(t)

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50 - 10
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 10 + 5
        y = self.grid_pos[1] * 50 + 10
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        self.data_tkjack = tkJack(self.root, self.mod, self.data_jack, "Data")
        self.data_tkjack.place(x=10, y=400)

        dpi = 80
        size = (380 / dpi, 350 / dpi)
        fig = Figure(figsize=size, dpi=dpi)
        fig.set_tight_layout(True)
        self.fig_canvas = FigureCanvasTkAgg(fig, self.root)
        self.fig_canvas.get_tk_widget().place(x=10, y=10)

        ax = fig.add_subplot()
        self.plot_lines = [
            Line2D([], [], color=f"C{i}") for i in range(Module.channels)
        ]
        for line in self.plot_lines:
            ax.add_line(line)
        ax.set_xlim([0, self.time_div])
        ax.set_ylim([-1000, 30000])
        ax.xaxis.set_ticklabels([])
        ax.yaxis.set_ticklabels([])
        ax.tick_params(direction="in", left=True, right=True, top=True, bottom=True)
        ax.grid(which="both")

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.data_tkjack.update_display(1)

                for i in range(self.mod.channels):
                    while (
                        len(self.timeseries[i]) >= 2
                        and self.timeseries[i][-1] - self.timeseries[i][0]
                        > self.time_div
                    ):
                        self.timeseries[i].pop(0)
                        self.dataseries[i].pop(0)

                for i, line in enumerate(self.plot_lines):
                    line.set_data(
                        [ts - self.timeseries[i][0] for ts in self.timeseries[i]],
                        self.dataseries[i],
                    )
                self.fig_canvas.draw()
                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError:
                self.shutdown()
                break

    def shutdown(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def module_task(self):
        while True:
            self.mod.update()
            await asyncio.sleep(1 / self.mod.packet_rate)

    async def quit(self):
        self.loop.stop()

    def patching_callback(self, state):
        self.data_tkjack.patching_callback(state)

    async def random_square_wave(self):
        while True:
            t = time.time()
            self.dataseries[0].append(
                (16000 if round(t) % 2 == 0 else 0) + random.random() * 1000
            )
            self.timeseries[0].append(t)
            while (
                len(self.timeseries[0]) > 0
                and self.timeseries[0][0] < t - self.time_div
            ):
                self.timeseries[0].pop(0)
                self.dataseries[0].pop(0)
            await asyncio.sleep(random.random() / 100)

    async def sin_wave(self):
        while True:
            t = time.time()
            self.dataseries[0].append(8000 * np.sin(t) + 8000)
            self.timeseries[0].append(t)
            while (
                len(self.timeseries[0]) > 0
                and self.timeseries[0][0] < t - self.time_div
            ):
                self.timeseries[0].pop(0)
                self.dataseries[0].pop(0)
            await asyncio.sleep(1 / 1000)

    async def triangle_wave(self):
        val = 0
        up = True
        while True:
            t = time.time()
            if up:
                val += 80
                if val == 16000:
                    up = False
            else:
                val -= 80
                if val == 0:
                    up = True
            self.dataseries[0].append(val)
            self.timeseries[0].append(t)
            while (
                len(self.timeseries[0]) > 0
                and self.timeseries[0][0] < t - self.time_div
            ):
                self.timeseries[0].pop(0)
                self.dataseries[0].pop(0)
            await asyncio.sleep(1 / 100)


class OscilloscopeEventHandler(EventHandler):
    def __init__(self, app: Oscilloscope) -> None:
        self.app = app

    def patch(self, state: PatchState) -> None:
        self.app.patching_callback(state)

    def halt(self) -> None:
        self.app.shutdown()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Oscilloscope(loop)
    loop.run_forever()
    loop.close()
