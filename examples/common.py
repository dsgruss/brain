import colorsys
import numpy as np
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
        color = hsv_to_string_rgb(hue, saturation, value)
        self.light.delete("light")
        self.light.create_oval(5, 5, 20, 20, fill=color, tags="light")


def hsv_to_string_rgb(hue: int, saturation: int, value: int) -> str:
    """hue -> 0, 359; saturation -> 0, 100; value -> 0, 100"""
    r, g, b = colorsys.hsv_to_rgb(hue / 360, saturation / 100, value / 100)
    r = int(r * 255)
    g = int(g * 255)
    b = int(b * 255)
    return f"#{r:02x}{g:02x}{b:02x}"


class tkKnob(tk.Frame):
    def __init__(self, parent, label, color, variable, from_, to) -> None:
        super().__init__(master=parent, width=50)
        self.color = color
        self.variable = variable
        self.from_ = from_
        self.to = to

        self.canvas = tk.Canvas(master=self, height=45, width=50)
        self.canvas.grid(row=0, column=0, pady=0)
        self.canvas.create_arc(
            5, 5, 45, 45, start=-60, extent=300, style=tk.ARC, width=2
        )
        self.canvas.bind("<Button-1>", self.drag_start)
        self.canvas.bind("<B1-Motion>", self.drag_motion)

        self.text = tk.Label(self, text=label)
        self.text.grid(row=1, column=0, pady=0)

        self.variable.set(np.clip(self.variable.get(), from_, to))
        self.val = (
            (self.variable.get() - self.from_) * 300 / (self.to - self.from_)
        )  # degrees
        self.redraw()

    def degrees_to_pos(self, theta):
        theta += 120
        return 25 + 20 * np.cos(np.pi * theta / 180), 25 + 20 * np.sin(
            np.pi * theta / 180
        )

    def drag_start(self, event):
        self.drag_x = event.x
        self.drag_y = event.y
        self.initial_val = self.val

    def drag_motion(self, event):
        self.val = np.clip(self.initial_val - event.y + self.drag_y, 0, 300)
        self.variable.set(self.val / 300 * (self.to - self.from_) + self.from_)
        self.redraw()

    def redraw(self):
        x, y = self.degrees_to_pos(self.val)
        self.canvas.delete("pointer")
        self.canvas.create_oval(
            x - 4,
            y - 4,
            x + 4,
            y + 4,
            fill=hsv_to_string_rgb(self.color, 100, 100),
            tags="pointer",
        )
