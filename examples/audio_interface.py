import asyncio
import numpy as np
import sounddevice as sd
import tkinter as tk
import threading

from collections import deque

from brain import module

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class Empty(Exception):
    "Exception raised when OverwriteBuffer is accessed empty"
    pass


class OverwriteBuffer:
    """A thread-safe queue that drops the oldest items when another one is added that would
    otherwise increase the count beyond `maxsize`. In this way the time delta between the first and
    last items is minimized and events will roughly remain in sync. By default, it will block while
    waiting for exclusive access to the queue, but will not block while waiting for new items."""

    def __init__(self, maxsize):
        self.maxsize = maxsize
        self.buffer = deque()
        self.buffer_lock = threading.Lock()

    def put(self, item):
        with self.buffer_lock:
            self.buffer.appendleft(item)
            while len(self.buffer) >= self.maxsize:
                self.buffer.pop()

    def get(self):
        with self.buffer_lock:
            if len(self.buffer) == 0:
                raise Empty
            else:
                return self.buffer.pop()


class AudioInterface:
    name = "Audio Interface"
    grid_size = (4, 10)
    grid_pos = (12, 0)

    def __init__(self, loop):
        self.loop = loop

        hostapis = {api["name"]: api for api in sd.query_hostapis()}
        for api in ["Windows WASAPI", "MME", "Windows DirectSound"]:
            if api in hostapis:
                default_device = hostapis[api]["default_output_device"]
                break
        else:
            default_device = sd.default.device["output"]

        logging.info("Using device " + sd.query_devices(default_device)["name"])

        self.ui_setup()
        loop.create_task(self.ui_task())

        self.mod = module.Module(
            self.name, self.patching_callback, process_callback=self.data_callback
        )
        self.indest = self.mod.add_input("Audio In")
        self.leveldest = self.mod.add_input("Level")

        self.audio_buffer = OverwriteBuffer(self.mod.buffer_size)
        self.level_buffer = OverwriteBuffer(self.mod.buffer_size)
        self.block_size = round(self.mod.sample_rate / self.mod.packet_rate)
        s = sd.OutputStream(
            device=default_device,
            samplerate=self.mod.sample_rate,
            channels=1,
            dtype=self.mod.sample_type,
            blocksize=self.block_size,
            callback=self.audio_callback,
        )

        s.start()
        self.mod.start()

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 50
        y = self.grid_pos[1] * 50 + 50
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        self.cbinval = tk.BooleanVar()
        self.cbin = tk.Checkbutton(
            self.root,
            text="Audio In",
            variable=self.cbinval,
            command=self.in_check_handler,
        )
        self.cbin.place(x=10, y=50)
        self.cblevelval = tk.BooleanVar()
        self.cblevel = tk.Checkbutton(
            self.root,
            text="Level",
            variable=self.cblevelval,
            command=self.level_check_handler,
        )
        self.cblevel.place(x=10, y=90)

        tk.Label(self.root, text=self.name).place(x=10, y=10)
        tk.Button(self.root, text="Quit", command=self.shutdown).place(x=10, y=170)

        self.statusbar = tk.Label(
            self.root, text="Loading...", bd=1, relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    def data_callback(self):
        self.audio_buffer.put(self.indest.get_data())
        self.level_buffer.put(self.leveldest.get_data())

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError:
                self.shutdown()
                break

    def in_check_handler(self):
        self.indest.set_patch_enabled(self.cbinval.get())

    def level_check_handler(self):
        self.leveldest.set_patch_enabled(self.cblevelval.get())

    def shutdown(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def quit(self):
        self.loop.stop()

    def patching_callback(self, state):
        self.statusbar.config(text=str(state))

    def audio_callback(self, outdata, frames, time, status):
        try:
            data = self.audio_buffer.get()
            level = self.level_buffer.get()

            outdata[:] = np.zeros((self.block_size, 1))
            for i in range(self.mod.channels):
                outdata[:, 0] += (data[:, i] * (level[0, i] / (4 * 16000))).astype(int)
        except Empty:
            outdata[:] = np.zeros((self.block_size, 1))


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = AudioInterface(loop)
    loop.run_forever()
    loop.close()
