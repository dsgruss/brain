import asyncio
import tkinter as tk

import brain

import logging

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)


class Manager:
    name = "Global State Control"

    grid_size = (4, 9)
    grid_pos = (0, 9)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

        self.mod = brain.Module(self.name, ManagerEventHandler(self))

        self.ui_setup()
        loop.create_task(self.ui_task())
        loop.create_task(self.module_task())

    def ui_setup(self):
        self.root = tk.Tk()
        w = self.grid_size[0] * 50 - 10
        h = self.grid_size[1] * 50
        x = self.grid_pos[0] * 50 + 10 + 5
        y = self.grid_pos[1] * 50 + 50
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.title(self.name)

        tk.Label(self.root, text=self.name).place(x=10, y=10)
        tk.Button(
            self.root, text="🔌    Close All", command=self.mod.halt_all, width=22
        ).place(x=10, y=170)

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

    def halt(self) -> None:
        self.app.shutdown()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = Manager(loop)
    loop.run_forever()
    loop.close()
