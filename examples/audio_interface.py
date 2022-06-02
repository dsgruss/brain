import argparse
import asyncio
import numpy as np
import sounddevice as sd
import tkinter as tk

from queue import Queue

import brain
from common import tkJack

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class AudioInterface:
    name = "Audio Interface"
    grid_size = (4, 9)

    def __init__(self, loop: asyncio.AbstractEventLoop, args: argparse.Namespace):
        self.loop = loop
        self.grid_pos = (args.gridx, args.gridy)
        self.color = args.color

        hostapis = {api["name"]: api for api in sd.query_hostapis()}
        for api in ["Windows WASAPI", "MME", "Windows DirectSound"]:
            if api in hostapis:
                self.default_device = hostapis[api]["default_output_device"]
                break
        else:
            self.default_device = sd.default.device["output"]

        logging.info("Using device " + sd.query_devices(self.default_device)["name"])

        self.mod = brain.Module(
            self.name, AudioInterfaceEventHandler(self), use_block_callback=True
        )
        self.in_jack = self.mod.add_input("Audio In")
        self.audio_buffer = Queue(brain.BUFFER_SIZE)

        self.ui_setup()
        loop.create_task(self.ui_task())
        loop.create_task(self.module_task())
        loop.create_task(self.audio_task())

    async def audio_task(self):
        s = sd.OutputStream(
            device=self.default_device,
            samplerate=brain.SAMPLE_RATE,
            channels=1,
            dtype=brain.SAMPLE_TYPE,
            blocksize=brain.BLOCK_SIZE,
            callback=self.audio_callback,
        )

        with s:
            while True:
                await asyncio.sleep(5)

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50 - 10
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 10 + 5
        y = self.grid_pos[1] * 50 + 10
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        self.in_tkjack = tkJack(self.root, self.mod, self.in_jack, "Audio In")
        self.in_tkjack.place(x=10, y=50)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    def data_callback(self, data):
        if not self.audio_buffer.full():
            self.audio_buffer.put(data[0].copy())
        assert data[0].shape == (48, 8)
        assert data.dtype == np.int16
        return np.zeros(1)

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.in_tkjack.update_display()

                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError as t:
                logging.info(t)
                self.shutdown()
                break

    async def module_task(self):
        while True:
            self.mod.update()
            await asyncio.sleep(1 / brain.PACKET_RATE)

    def shutdown(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def quit(self):
        logging.info("Quit invoked")
        self.loop.stop()

    def patching_callback(self, state):
        self.in_tkjack.patching_callback(state)

    def audio_callback(
        self, outdata: np.ndarray, frames: int, time, status: sd.CallbackFlags
    ) -> None:
        if frames != brain.BLOCK_SIZE:
            logging.info("Frame mismatch")
            raise ValueError
        if status:
            logging.info(status)
            raise ValueError
        if not self.audio_buffer.empty():
            data = self.audio_buffer.get()
            outdata.fill(0)
            for i in range(brain.CHANNELS):
                outdata[:, 0] += data[:, i]
        else:
            outdata.fill(0)


class AudioInterfaceEventHandler(brain.EventHandler):
    def __init__(self, app: AudioInterface) -> None:
        self.app = app

    def patch(self, state: brain.PatchState) -> None:
        self.app.patching_callback(state)

    def block_process(self, input: np.ndarray) -> np.ndarray:
        return self.app.data_callback(input)

    def halt(self) -> None:
        self.app.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audio Interface")
    parser.add_argument(
        "--gridx", default=32, type=int, help="Window X position in the grid"
    )
    parser.add_argument(
        "--gridy", default=0, type=int, help="Window Y position in the grid"
    )
    parser.add_argument(
        "--color", default=240, type=int, help="HSV Hue color of the interface"
    )
    parser.add_argument("--id", default=0, type=int, help="Unique identifier postfix")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    app = AudioInterface(loop, args)
    loop.run_forever()
    logging.info("Loop is broken")
    loop.close()
