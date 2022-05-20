import asyncio
import numpy as np
import sounddevice as sd
import tkinter as tk
import threading

from collections import deque

from brain import module

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class AudioInterface:
    channels = 8
    updatefreq = 1000  # Hz
    name = "Audio Interface"
    grid_size = (4, 10)
    grid_pos = (12, 0)
    audio_buffer = deque()
    audio_buffer_lock = threading.Lock()
    audio_buffer_size = 100

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

        s = sd.OutputStream(
            device=default_device,
            samplerate=48000,
            channels=1,
            dtype=np.int16,
            blocksize=48,
            callback=self.audio_callback,
        )
        s.start()

        self.ui_setup()
        loop.create_task(self.ui_task())

        self.module_interface = module.Module(self.name, self.patching_callback)
        self.indest = self.module_interface.add_input(
            self.data_callback, name="Audio In"
        )

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

        tk.Label(self.root, text=self.name).place(x=10, y=10)
        tk.Button(self.root, text="Quit", command=self.shutdown).place(x=10, y=170)

        self.statusbar = tk.Label(
            self.root, text="Loading...", bd=1, relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    def data_callback(self, data, sample_rate):
        with self.audio_buffer_lock:
            self.audio_buffer.appendleft(np.frombuffer(data, dtype=np.int16))
            while len(self.audio_buffer) >= self.audio_buffer_size:
                self.audio_buffer.pop()

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError:
                self.shutdown()
                break

    def in_check_handler(self):
        self.indest.patch_enabled(self.cbinval.get())

    def shutdown(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def quit(self):
        self.loop.stop()

    def patching_callback(self, state):
        self.statusbar.config(text=str(state))

    def audio_callback(self, outdata, frames, time, status):
        data = np.zeros((48, 8))
        with self.audio_buffer_lock:
            if len(self.audio_buffer) > 0:
                data = self.audio_buffer.pop()
        data = data.reshape((48, 8))
        outdata[:, 0] = data[:, 0]


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = AudioInterface(loop)
    loop.run_forever()
    loop.close()
