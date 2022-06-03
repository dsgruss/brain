import asyncio
import honcho.process
import honcho.printer
import multiprocessing
import queue
import tkinter as tk

from collections import Counter

import brain

import logging

logging.basicConfig(
    format="%(asctime)s manager              | %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    level=logging.DEBUG,
)


class Manager:
    name = "Global State Control"

    grid_size = (4, 9)
    grid_pos = (0, 10)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

        self.mod = brain.Module(self.name, ManagerEventHandler(self))

        self.colors = [
            ("cyan", str(36) + ";1", 180),
            ("yellow", str(33) + ";1", 60),
            ("green", str(32) + ";1", 120),
            ("magenta", str(35) + ";1", 300),
            ("red", str(31) + ";1", 0),
            ("blue", str(34) + ";1", 240),
        ]

        self.processes = [
            ("midi_to_cv", "examples/midi_to_cv.py", "Midi to CV"),
            ("asr_envelope", "examples/asr_envelope.py", "ASR Envelope"),
            ("oscillator", "examples/oscillator.py", "Oscillator"),
            ("mixer", "examples/mixer.py", "Mixer"),
            ("filter", "examples/filter.py", "Filter"),
            ("audio_interface", "examples/audio_interface.py", "Audio Interface"),
            ("oscilloscope", "examples/oscilloscope.py", "Oscilloscope"),
        ]

        self.gridx = 0
        self.gridy = 0
        self.color_idx = 0
        self.process_counter = Counter()
        self.events = multiprocessing.Queue()
        self.printer = honcho.printer.Printer(width=20)

        self.ui_setup()
        loop.create_task(self.ui_task())
        loop.create_task(self.module_task())
        loop.create_task(self.printer_task())

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50 - 10
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 10 + 5
        y = self.grid_pos[1] * 50 + 10
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        tk.Label(self.root, text=self.name).place(x=10, y=10)
        tk.Button(
            self.root, text="🔌    Close All", command=self.mod.halt_all, width=22
        ).place(x=10, y=50)

        for i, process in enumerate(self.processes):
            tk.Button(
                self.root,
                text=process[2],
                command=lambda x=process[1], y=process[0]: self.launch(x, y),
                width=22,
            ).place(x=10, y=100 + 30 * i)

        self.statusbar = tk.Label(
            self.root, text="Loading...", bd=1, relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError:
                self.shutdown()
                break

    async def module_task(self):
        while True:
            self.mod.update()
            await asyncio.sleep(1 / brain.PACKET_RATE)

    async def printer_task(self, interval=(1 / 60)):
        while True:
            try:
                msg = self.events.get(timeout=0.1)
            except queue.Empty:
                await asyncio.sleep(interval)
                continue

            if msg.type == "line":
                self.printer.write(msg)
            elif msg.type == "start":
                logging.info("%s started (pid=%s)" % (msg.name, msg.data["pid"]))
            elif msg.type == "stop":
                logging.info("%s stopped (rc=%s)" % (msg.name, msg.data["returncode"]))

    def launch(self, dest, id):
        p = multiprocessing.Process(
            target=honcho.process.Process(
                [
                    "python",
                    dest,
                    "--gridx",
                    str(self.gridx),
                    "--gridy",
                    str(self.gridy),
                    "--color",
                    str(self.colors[self.color_idx][2]),
                    "--id",
                    str(self.process_counter[id]),
                ],
                name=id + "." + str(self.process_counter[id]),
                colour=self.colors[self.color_idx][1],
            ).run,
            args=(self.events,),
        )
        p.start()

        self.gridx += 4
        if self.gridx == 36:
            self.gridx = 4
            self.gridy += 10
        self.color_idx = (self.color_idx + 1) % len(self.colors)
        self.process_counter[id] += 1

    def shutdown(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def quit(self):
        self.loop.stop()

    def patching_callback(self, state):
        self.statusbar.config(text=str(state))


class ManagerEventHandler(brain.EventHandler):
    def __init__(self, app: Manager) -> None:
        self.app = app

    def patch(self, state: brain.PatchState) -> None:
        self.app.patching_callback(state)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Manager(loop)
    loop.run_forever()
    loop.close()
