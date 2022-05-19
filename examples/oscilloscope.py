import asyncio
import matplotlib
import random
import tkinter
import time

from tkinter import ttk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.lines import Line2D

from brain import module

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
matplotlib.use("TkAgg")


class Oscilloscope:
    name = "Oscilloscope"
    dataseries = []
    timeseries = []

    def __init__(self, loop):
        self.loop = loop

        self.module_interface = module.Module(self.name)
        self.data = self.module_interface.add_input(self.data_callback, name="Data")

        loop.create_task(self.ui_task())
        loop.create_task(self.data_run())

    def data_callback(self, data):
        pass

    async def ui_task(self, interval=(1 / 30)):
        root = tkinter.Tk()
        root.geometry("400x500+260+50")

        self.cbdataval = tkinter.BooleanVar()

        self.cbdata = ttk.Checkbutton(
            root, text="Data", variable=self.cbdataval, command=self.data_check_handler
        )
        self.cbdata.place(x=10, y=430)

        ttk.Label(root, text=self.name).place(x=100, y=430)
        ttk.Button(root, text="Quit", command=self.shutdown).place(x=250, y=430)

        dpi = 80
        size = (380 / dpi, 350 / dpi)
        fig = Figure(figsize=size, dpi=dpi)
        fig.set_tight_layout(True)
        fig_canvas = FigureCanvasTkAgg(fig, root)
        fig_canvas.get_tk_widget().place(x=10, y=10)

        ax = fig.add_subplot()
        line = Line2D(self.dataseries, self.timeseries)
        ax.add_line(line)
        ax.set_xlim([0, 4])
        ax.xaxis.set_ticklabels([])
        ax.yaxis.set_ticklabels([])
        ax.tick_params(direction="in", left=True, right=True, top=True, bottom=True)
        ax.grid(which="both")

        while True:
            t = time.time()
            line.set_data([ts - t + 4 for ts in self.timeseries], self.dataseries)
            fig_canvas.draw()
            root.update()
            await asyncio.sleep(interval)

    def data_check_handler(self):
        self.data.patch_enabled(self.cbdataval.get())

    def shutdown(self):
        self.loop.stop()

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
