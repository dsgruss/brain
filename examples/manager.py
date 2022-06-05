import asyncio
import time
import honcho.process
import honcho.printer
import multiprocessing
import queue
import tkinter as tk

from collections import defaultdict

import brain

import logging

logging.basicConfig(
    format="%(asctime)s manager              | %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    level=logging.DEBUG,
)


class Manager:
    name = "Global State Control"

    grid_size = (4, 19)
    grid_pos = (0, 0)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.id = "root:virtual_examples:manager"

        self.mod = brain.Module(self.name, ManagerEventHandler(self), id=self.id)

        self.colors = [
            ("cyan", str(36) + ";1", 180),
            ("yellow", str(33) + ";1", 60),
            ("green", str(32) + ";1", 120),
            ("magenta", str(35) + ";1", 300),
            ("red", str(31) + ";1", 0),
            ("blue", str(34) + ";1", 240),
        ]

        self.processes = {
            "midi_to_cv": ("examples/midi_to_cv.py", "Midi to CV"),
            "asr_envelope": ("examples/asr_envelope.py", "ASR Envelope"),
            "oscillator": ("examples/oscillator.py", "Oscillator"),
            "mixer": ("examples/mixer.py", "Mixer"),
            "filter": ("examples/filter.py", "Filter"),
            "audio_interface": ("examples/audio_interface.py", "Audio Interface"),
            "oscilloscope": ("examples/oscilloscope.py", "Oscilloscope"),
            "reverb": ("examples/reverb.py", "Reverb")
        }

        self.gridx = 4
        self.gridy = 0
        self.color_idx = 0
        self.open_processes = defaultdict(dict)
        self.events = multiprocessing.Queue()
        self.printer = honcho.printer.Printer(width=20)
        self.snapshots = init_patch

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
            self.root, text="🔌    Close All", command=self.close_all, width=22
        ).place(x=10, y=50)
        tk.Button(
            self.root, text="Save Preset", command=self.get_snapshots, width=22
        ).place(x=10, y=80)
        tk.Button(
            self.root, text="Load Preset", command=self.set_snapshots, width=22
        ).place(x=10, y=110)

        for i, process in enumerate(self.processes.items()):
            tk.Button(
                self.root,
                text=process[1][1],
                command=lambda x=process[1][0], y=process[0]: self.launch(x, y),
                width=22,
            ).place(x=10, y=200 + 30 * i)

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
                id = msg.name.split(".")[0]
                id_idx = int(msg.name.split(".")[1])
                del self.open_processes[id][id_idx]

    def launch(self, dest, id, id_idx=None):
        if id_idx is None:
            # Find the next open id the slow way
            id_idx = 0
            used_idxs = self.open_processes[id].keys()
            while id_idx in used_idxs:
                id_idx += 1

        target = honcho.process.Process(
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
                str(id_idx),
            ],
            name=id + "." + str(id_idx),
            colour=self.colors[self.color_idx][1],
        )
        self.open_processes[id][id_idx] = target

        p = multiprocessing.Process(target=target.run, args=(self.events,))
        p.start()

        self.gridx += 4
        if self.gridx == 36:
            self.gridx = 4
            self.gridy += 10
        self.color_idx = (self.color_idx + 1) % len(self.colors)

    def close_all(self):
        self.mod.halt_all()
        self.gridx = 4
        self.gridy = 0

    def shutdown(self):
        for task in asyncio.all_tasks():
            task.cancel()
        asyncio.ensure_future(self.quit())

    async def quit(self):
        self.loop.stop()

    def patching_callback(self, state):
        self.statusbar.config(text=str(state))

    def get_snapshots(self):
        self.mod.get_all_snapshots()

    def recieved_snapshot(self, uuid, snapshot):
        if uuid != self.id:
            self.snapshots[uuid] = snapshot

    def set_snapshots(self):
        logging.info("Snapshot items: " + str(self.snapshots))
        launched_process = False
        for k, v in self.snapshots.items():
            id = k.split(":")[-2]
            id_idx = int(k.split(":")[-1])
            if id_idx not in self.open_processes[id]:
                self.launch(self.processes[id][0], id, id_idx)
                launched_process = True
        if launched_process:
            time.sleep(1)
        self.mod.set_all_snapshots(self.snapshots.values())


class ManagerEventHandler(brain.EventHandler):
    def __init__(self, app: Manager) -> None:
        self.app = app

    def patch(self, state: brain.PatchState) -> None:
        self.app.patching_callback(state)

    def recieved_snapshot(self, uuid, snapshot) -> None:
        self.app.recieved_snapshot(uuid, snapshot)


init_patch = {
    "root:virtual_examples:midi_to_cv:0": b'{"message": "SNAPSHOTRESPONSE", "uuid": "root:virtual_examples:midi_to_cv:0", "data": "", "patched": [{"input_uuid": "root:virtual_examples:filter:0", "input_jack_id": "1", "output_uuid": "root:virtual_examples:midi_to_cv:0", "output_jack_id": "0"}, {"input_uuid": "root:virtual_examples:oscillator:0", "input_jack_id": "0", "output_uuid": "root:virtual_examples:midi_to_cv:0", "output_jack_id": "0"}, {"input_uuid": "root:virtual_examples:asr_envelope:0", "input_jack_id": "0", "output_uuid": "root:virtual_examples:midi_to_cv:0", "output_jack_id": "1"}]}',
    "root:virtual_examples:asr_envelope:0": b'{"message": "SNAPSHOTRESPONSE", "uuid": "root:virtual_examples:asr_envelope:0", "data": "", "patched": [{"input_uuid": "root:virtual_examples:asr_envelope:0", "input_jack_id": "0", "output_uuid": "root:virtual_examples:midi_to_cv:0", "output_jack_id": "1"}, {"input_uuid": "root:virtual_examples:mixer:0", "input_jack_id": "3", "output_uuid": "root:virtual_examples:asr_envelope:0", "output_jack_id": "1"}]}',
    "root:virtual_examples:oscillator:0": b'{"message": "SNAPSHOTRESPONSE", "uuid": "root:virtual_examples:oscillator:0", "data": "", "patched": [{"input_uuid": "root:virtual_examples:oscillator:0", "input_jack_id": "0", "output_uuid": "root:virtual_examples:midi_to_cv:0", "output_jack_id": "0"}, {"input_uuid": "root:virtual_examples:filter:0", "input_jack_id": "0", "output_uuid": "root:virtual_examples:oscillator:0", "output_jack_id": "3"}]}',
    "root:virtual_examples:filter:0": b'{"message": "SNAPSHOTRESPONSE", "uuid": "root:virtual_examples:filter:0", "data": "", "patched": [{"input_uuid": "root:virtual_examples:filter:0", "input_jack_id": "0", "output_uuid": "root:virtual_examples:oscillator:0", "output_jack_id": "3"}, {"input_uuid": "root:virtual_examples:filter:0", "input_jack_id": "1", "output_uuid": "root:virtual_examples:midi_to_cv:0", "output_jack_id": "0"}, {"input_uuid": "root:virtual_examples:mixer:0", "input_jack_id": "0", "output_uuid": "root:virtual_examples:filter:0", "output_jack_id": "2"}]}',
    "root:virtual_examples:mixer:0": b'{"message": "SNAPSHOTRESPONSE", "uuid": "root:virtual_examples:mixer:0", "data": "", "patched": [{"input_uuid": "root:virtual_examples:mixer:0", "input_jack_id": "0", "output_uuid": "root:virtual_examples:filter:0", "output_jack_id": "2"}, {"input_uuid": "root:virtual_examples:mixer:0", "input_jack_id": "3", "output_uuid": "root:virtual_examples:asr_envelope:0", "output_jack_id": "1"}, {"input_uuid": "root:virtual_examples:audio_interface:0", "input_jack_id": "0", "output_uuid": "root:virtual_examples:mixer:0", "output_jack_id": "6"}]}',
    "root:virtual_examples:audio_interface:0": b'{"message": "SNAPSHOTRESPONSE", "uuid": "root:virtual_examples:audio_interface:0", "data": "", "patched": [{"input_uuid": "root:virtual_examples:audio_interface:0", "input_jack_id": "0", "output_uuid": "root:virtual_examples:mixer:0", "output_jack_id": "6"}]}',
}

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Manager(loop)
    loop.run_forever()
    loop.close()
