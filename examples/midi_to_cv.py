import asyncio
import mido
import numpy as np
import time
import tkinter as tk

from dataclasses import dataclass

from brain import Module
from common import tkJack

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


@dataclass
class Voice:
    note: int
    on: bool
    timestamp: int


class MidiToCV:
    """Module to convert a midi stream to control voltages"""

    timestamp = 0

    name = "Midi to CV converter"
    color = 280  # hue

    grid_size = (4, 9)
    grid_pos = (0, 0)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

        logging.info("Opening all midi inputs by default...")
        for inp in mido.get_input_names():
            self.loop.create_task(self.midi_task(mido.open_input(inp)))

        self.mod = Module(
            self.name, self.patching_callback, abort_callback=self.shutdown
        )

        self.voices = [Voice(0, False, 0) for _ in range(Module.channels)]
        self.mod_wheel = 0

        self.note_jack = self.mod.add_output(name="Note", color=self.color)
        self.gate_jack = self.mod.add_output(name="Gate", color=self.color)
        self.velo_jack = self.mod.add_output(name="Velocity", color=self.color)
        self.lift_jack = self.mod.add_output(name="Lift", color=self.color)
        self.piwh_jack = self.mod.add_output(name="Pitch Wheel", color=self.color)
        self.mdwh_jack = self.mod.add_output(name="Mod Wheel", color=self.color)

        self.ui_setup()
        self.loop.create_task(self.ui_task())

        self.loop.create_task(self.output_task())
        self.mod.start()

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50 - 10
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 10 + 5
        y = self.grid_pos[1] * 50 + 10
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        self.note_tkjack = tkJack(self.root, self.note_jack, "Note")
        self.note_tkjack.place(x=10, y=50)
        self.gate_tkjack = tkJack(self.root, self.gate_jack, "Gate")
        self.gate_tkjack.place(x=10, y=90)

        self.mdwh_tkjack = tkJack(self.root, self.mdwh_jack, "Mod Wheel")
        self.mdwh_tkjack.place(x=10, y=130)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.note_tkjack.update_display(1)
                if any(v.on for v in self.voices):
                    self.gate_tkjack.update_display(1)
                else:
                    self.gate_tkjack.update_display(0)
                self.mdwh_tkjack.update_display(self.mod_wheel / 128)

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
        for jack in [self.note_tkjack, self.gate_tkjack, self.mdwh_tkjack]:
            jack.patching_callback(state)

    async def midi_task(self, port, interval=(1 / 60)):
        while True:
            for message in port.iter_pending():
                logging.info(message)
                self.timestamp += 1
                if message.type == "note_off":
                    for v in self.voices:
                        if v.note == message.note and v.on:
                            v.on = False
                            v.timestamp = self.timestamp
                elif message.type == "note_on":
                    # First see if we can take the oldest voice that has been released
                    voices_off = sorted(
                        (v for v in self.voices if not v.on),
                        key=lambda x: x.timestamp,
                    )
                    if len(voices_off) > 0:
                        voices_off[0].note = message.note
                        voices_off[0].on = True
                        voices_off[0].timestamp = self.timestamp
                    else:
                        # Otherwise, steal a voice. In this case, take the oldest note played. We
                        # also have a choice of whether to just change the pitch (done here), or to
                        # shut the note off and retrigger.
                        voice_steal = min(self.voices, key=lambda x: x.timestamp)
                        voice_steal.note = message.note
                        voice_steal.timestamp = self.timestamp
                elif message.type == "control_change":
                    if message.control == 1:
                        self.mod_wheel = message.value
                logging.info("\n\t".join([str(v) for v in self.voices]))
            await asyncio.sleep(interval)

    async def output_task(self):
        """Send the data as CV over over all requested ports and addresses at the configured sample
        rate"""

        t = time.perf_counter()
        voct_data = np.zeros((1, 8), dtype=Module.sample_type)
        gate_data = np.zeros((1, 8), dtype=Module.sample_type)
        mdwh_data = np.zeros((1, 8), dtype=Module.sample_type)
        while True:
            dt = time.perf_counter() - t
            while dt > (1 / Module.packet_rate):
                for i, v in enumerate(self.voices):
                    voct_data[0, i] = v.note * 256
                    gate_data[0, i] = 16000 if v.on else 0
                    mdwh_data[0, i] = self.mod_wheel * 256

                self.note_jack.send(voct_data.tobytes())
                self.gate_jack.send(gate_data.tobytes())
                self.mdwh_jack.send(mdwh_data.tobytes())
                t += 1 / Module.packet_rate
                dt = time.perf_counter() - t

            await asyncio.sleep(1 / Module.packet_rate)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = MidiToCV(loop)
    loop.run_forever()
    loop.close()
