import asyncio
import numpy as np
import sounddevice as sd
import tkinter as tk
import threading

from collections import deque

from brain import module
from common import tkJack

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
    color = 240  # hue

    grid_size = (4, 9)
    grid_pos = (16, 0)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

        hostapis = {api["name"]: api for api in sd.query_hostapis()}
        for api in ["Windows WASAPI", "MME", "Windows DirectSound"]:
            if api in hostapis:
                default_device = hostapis[api]["default_output_device"]
                break
        else:
            default_device = sd.default.device["output"]

        logging.info("Using device " + sd.query_devices(default_device)["name"])

        self.mod = module.Module(
            self.name,
            self.patching_callback,
            process_callback=self.data_callback,
            abort_callback=self.shutdown,
        )
        self.in_jack = self.mod.add_input("Audio In")
        self.level_jack = self.mod.add_input("Level")

        self.level_value = 0

        self.ui_setup()
        loop.create_task(self.ui_task())

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
        w = self.grid_size[0] * 50 - 10
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 10 + 5
        y = self.grid_pos[1] * 50 + 10
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        self.in_tkjack = tkJack(self.root, self.in_jack, "Audio In")
        self.in_tkjack.place(x=10, y=50)
        self.level_tkjack = tkJack(self.root, self.level_jack, "Level")
        self.level_tkjack.place(x=10, y=90)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    def data_callback(self):
        self.audio_buffer.put(self.in_jack.get_data())
        self.level_buffer.put(self.level_jack.get_data())

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                if self.mod.patch_state == module.PatchState.IDLE:
                    if self.in_jack.is_patched():
                        self.in_tkjack.set_color(self.in_jack.color, 100, 100)
                    else:
                        self.in_tkjack.set_color(0, 0, 0)
                    if self.level_jack.is_patched():
                        self.level_tkjack.set_color(
                            self.level_jack.color, 100, self.level_value
                        )
                    else:
                        self.level_tkjack.set_color(0, 0, 0)
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
        for jack in [self.in_tkjack, self.level_tkjack]:
            if state == module.PatchState.PATCH_TOGGLED:
                jack.set_color(77, 100, 100)
            elif state == module.PatchState.PATCH_ENABLED:
                jack.set_color(0, 0, 50)
            elif state == module.PatchState.BLOCKED:
                jack.set_color(0, 100, 100)

    def audio_callback(self, outdata, frames, time, status):
        try:
            data = self.audio_buffer.get()
            level = self.level_buffer.get()

            outdata[:] = np.zeros((self.block_size, 1))
            for i in range(self.mod.channels):
                outdata[:, 0] += (data[:, i] * (level[0, i] / (4 * 16000))).astype(int)
            self.level_value = min(max(level[0, :]) / 16000 * 100, 100)
        except Empty:
            outdata[:] = np.zeros((self.block_size, 1))


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = AudioInterface(loop)
    loop.run_forever()
    loop.close()
