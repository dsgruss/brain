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

    def __init__(self, loop):
        self.dataseries = [[] for _ in range(self.channels)]
        self.timeseries = [[] for _ in range(self.channels)]

        self.loop = loop

        self.ui_setup()
        loop.create_task(self.ui_task())

        self.module_interface = module.Module(self.name, self.patching_callback)
        self.data = self.module_interface.add_input(self.data_callback, name="Data")

        # loop.create_task(self.data_run())

    def data_callback(self, data):
        result = np.frombuffer(data, dtype=np.int16)
        result = result.reshape((len(result) // self.channels, self.channels))
        t = time.time()
        for i in range(self.channels):
            self.dataseries[i].append(result[0, i])
            self.timeseries[i].append(t)
            while len(self.timeseries[i]) > 0 and self.timeseries[i][0] < t - self.time_div:
                self.timeseries[i].pop(0)
                self.dataseries[i].pop(0)

    def ui_setup(self):
        self.root = tk.Tk()
        self.root.geometry("400x500+260+50")

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

    async def ui_task(self, interval=(1 / 30)):
        while True:
            t = time.time()
            for i, line in enumerate(self.plot_lines):
                line.set_data(
                    [ts - t + 4 for ts in self.timeseries[i]], self.dataseries[i]
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

    async def data_run(self):
        while True:
            t = time.time()
            self.dataseries.append(
                (0.75 if round(t) % 2 == 0 else 0.25) + random.random() / 10
            )
            self.timeseries.append(t)
            while len(self.timeseries) > 0 and self.timeseries[0] < t - 4:
                self.timeseries.pop(0)
                self.dataseries.pop(0)
            await asyncio.sleep(random.random() / 100)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Oscilloscope(loop)
    loop.run_forever()
    loop.close()
