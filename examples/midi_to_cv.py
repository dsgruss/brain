import argparse
import asyncio
import mido
import numpy as np
import tkinter as tk

from dataclasses import dataclass

import brain
from brain.constants import BLOCK_SIZE, CHANNELS, midi_note_to_voct
from common import tkJack

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


@dataclass
class Voice:
    note: int
    on: bool
    timestamp: int


class MidiToCV(brain.EventHandler):
    """Module to convert a midi stream to control voltages"""

    timestamp = 0

    name = "Midi to CV converter"
    grid_size = (4, 9)

    def __init__(self, loop: asyncio.AbstractEventLoop, args: argparse.Namespace):
        self.loop = loop
        self.grid_pos = (args.gridx, args.gridy)
        self.color = args.color

        logging.info("Opening all midi inputs by default...")
        for inp in mido.get_input_names():
            self.loop.create_task(self.midi_task(mido.open_input(inp)))

        self.mod = brain.Module(
            self.name,
            self,
            id="root:virtual_examples:midi_to_cv:" + str(args.id),
        )

        self.voices = [Voice(0, False, 0) for _ in range(brain.CHANNELS)]
        self.mod_wheel = 0

        self.note_jack = self.mod.add_output(name="Note", color=self.color)
        self.gate_jack = self.mod.add_output(name="Gate", color=self.color)
        self.velo_jack = self.mod.add_output(name="Velocity", color=self.color)
        self.lift_jack = self.mod.add_output(name="Lift", color=self.color)
        self.piwh_jack = self.mod.add_output(name="Pitch Wheel", color=self.color)
        self.mdwh_jack = self.mod.add_output(name="Mod Wheel", color=self.color)

        self.ui_setup()
        self.loop.create_task(self.ui_task())
        self.loop.create_task(self.module_task())

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50 - 10
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 10 + 5
        y = self.grid_pos[1] * 50 + 10
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        self.note_tkjack = tkJack(self.root, self.mod, self.note_jack, "Note")
        self.note_tkjack.place(x=10, y=50)
        self.gate_tkjack = tkJack(self.root, self.mod, self.gate_jack, "Gate")
        self.gate_tkjack.place(x=10, y=90)

        self.mdwh_tkjack = tkJack(self.root, self.mod, self.mdwh_jack, "Mod Wheel")
        self.mdwh_tkjack.place(x=10, y=130)

        tk.Label(self.root, text=self.name).place(x=10, y=10)

    async def ui_task(self, interval=(1 / 60)):
        while True:
            try:
                self.note_tkjack.update_display()
                self.gate_tkjack.update_display()
                self.mdwh_tkjack.update_display()

                self.root.update()
                await asyncio.sleep(interval)
            except tk.TclError:
                self.halt()
                break

    async def module_task(self):
        while True:
            self.mod.update()
            await asyncio.sleep(1 / brain.PACKET_RATE)

    def halt(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def quit(self):
        self.loop.stop()

    def patch(self, state):
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

    def process(self, input):
        """Send the data as CV over over all requested ports and addresses at the configured sample
        rate"""

        output = np.zeros((6, BLOCK_SIZE, CHANNELS), dtype=brain.SAMPLE_TYPE)

        for i, v in enumerate(self.voices):
            output[0, :, i].fill(midi_note_to_voct(v.note))
            output[1, :, i].fill(16000 if v.on else 0)
            output[5, :, i].fill(self.mod_wheel * 256)

        return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Midi to CV converter")
    parser.add_argument(
        "--gridx", default=0, type=int, help="Window X position in the grid"
    )
    parser.add_argument(
        "--gridy", default=0, type=int, help="Window Y position in the grid"
    )
    parser.add_argument(
        "--color", default=280, type=int, help="HSV Hue color of the interface"
    )
    parser.add_argument("--id", default=0, type=int, help="Unique identifier postfix")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    app = MidiToCV(loop, args)
    loop.run_forever()
    loop.close()
