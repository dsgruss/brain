import asyncio
import matplotlib
import numpy as np
import random
import tkinter as tk
import time

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.lines import Line2D

from brain import module

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
matplotlib.use("TkAgg")


class Oscilloscope:
    name = "Oscilloscope"
    channels = 8
    time_div = 4.0  # sec
    grid_size = (8, 10)
    grid_pos = (8, 0)

    def __init__(self, loop):
        self.dataseries = [[] for _ in range(self.channels)]
        self.timeseries = [[] for _ in range(self.channels)]

        self.loop = loop

        self.ui_setup()
        loop.create_task(self.ui_task())

        self.module_interface = module.Module(self.name, self.patching_callback)
        self.data = self.module_interface.add_input(self.data_callback, name="Data")

        # loop.create_task(self.random_square_wave())
        # loop.create_task(self.sin_wave())
        # loop.create_task(self.triangle_wave())

    def data_callback(self, data, sample_rate):
        result = np.frombuffer(data, dtype=np.int16)
        if len(self.timeseries[0]) == 0:
            t = 0
        else:
            t = self.timeseries[0][-1] + (1 / sample_rate)
        for i in range(self.channels):
            self.dataseries[i].append(result[i])
            self.timeseries[i].append(t)

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 50
        y = self.grid_pos[1] * 50 + 50
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        self.cbdataval = tk.BooleanVar()

        self.cbdata = tk.Checkbutton(
            self.root,
            text="Data",
            variable=self.cbdataval,
            command=self.data_check_handler,
        )
        self.cbdata.place(x=10, y=430)

        self.statusbar = tk.Label(
            self.root, text="Loading...", bd=1, relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

        tk.Button(self.root, text="Quit", command=self.shutdown).place(x=250, y=430)

        dpi = 80
        size = (380 / dpi, 350 / dpi)
        fig = Figure(figsize=size, dpi=dpi)
        fig.set_tight_layout(True)
        self.fig_canvas = FigureCanvasTkAgg(fig, self.root)
        self.fig_canvas.get_tk_widget().place(x=10, y=10)

        ax = fig.add_subplot()
        self.plot_lines = [Line2D([], [], color=f"C{i}") for i in range(self.channels)]
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
            for i in range(self.channels):
                while (
                    len(self.timeseries[i]) >= 2
                    and self.timeseries[i][-1] - self.timeseries[i][0] > self.time_div
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

    def data_check_handler(self):
        self.data.patch_enabled(self.cbdataval.get())

    def shutdown(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def quit(self):
        self.loop.stop()

    def patching_callback(self, state):
        self.statusbar.config(text=str(state))

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


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Oscilloscope(loop)
    loop.run_forever()
    loop.close()
