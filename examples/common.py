import colorsys
import tkinter as tk

from brain import Module, Jack, PatchState


class tkJack(tk.Frame):
    """tk display widget for an input or output jack"""

    def __init__(self, parent: tk.Tk, mod: Module, jack: Jack, text: str) -> None:
        super().__init__(master=parent)

        self.light = tk.Canvas(master=self, height=20, width=20)
        self.light.create_oval(5, 5, 20, 20, fill="#008080", tags="light")
        self.light.pack(side="left", fill="y")

        self.press_value = tk.BooleanVar()
        self.press_value.trace_add("write", self.checkbutton_handler)

        self.light.bind("<ButtonPress-1>", lambda _: self.press_value.set(True))
        self.light.bind("<ButtonRelease-1>", lambda _: self.press_value.set(False))

        self.checkbutton = tk.Checkbutton(
            master=self, text=text, variable=self.press_value
        )
        self.checkbutton.pack(side="left", fill="y")

        self.jack = jack
        self.patch_state = PatchState.IDLE
        self.mod = mod

    def checkbutton_handler(self, *_) -> None:
        self.mod.set_patch_enabled(self.jack, self.press_value.get())

    def patching_callback(self, state: PatchState) -> None:
        self.patch_state = state

    def update_display(self, display_value: float) -> None:
        if self.patch_state in (PatchState.IDLE, PatchState.PATCH_ENABLED):
            if self.patch_state == PatchState.IDLE:
                intensity = 100
            else:
                intensity = 50

            if self.mod.is_input(self.jack) and not self.mod.is_patched(self.jack):
                self.set_color(0, 0, 0)
            else:
                self.set_color(
                    self.mod.get_jack_color(self.jack),
                    100,
                    min(display_value * intensity, 100),
                )

            if self.patch_state == PatchState.PATCH_ENABLED:
                if self.mod.is_patch_member(self.jack):
                    self.set_color(0, 0, 100)
        elif self.patch_state == PatchState.PATCH_TOGGLED:
            self.set_color(77, 100, 100)
        elif self.patch_state == PatchState.BLOCKED:
            self.set_color(0, 100, 100)

    def set_color(self, hue: int, saturation: int, value: int) -> None:
        """hue -> 0, 359; saturation -> 0, 100; value -> 0, 100"""
        r, g, b = colorsys.hsv_to_rgb(hue / 360, saturation / 100, value / 100)
        r = int(r * 255)
        g = int(g * 255)
        b = int(b * 255)
        color = f"#{r:02x}{g:02x}{b:02x}"
        self.light.delete("light")
        self.light.create_oval(5, 5, 20, 20, fill=color, tags="light")
