import colorsys
import tkinter as tk

from brain import Jack, InputJack, PatchState


class tkJack(tk.Frame):
    """tk display widget for an input or output jack"""

    def __init__(self, parent: tk.Tk, jack: Jack, text: str) -> None:
        super().__init__(master=parent)

        self.light = tk.Canvas(master=self, height=20, width=20)
        self.light.create_oval(5, 5, 20, 20, fill="#008080", tags="light")
        self.light.pack(side="left", fill="y")

        self.checkbutton_value = tk.BooleanVar()
        self.checkbutton = tk.Checkbutton(
            master=self,
            text=text,
            variable=self.checkbutton_value,
            command=self.checkbutton_handler,
        )
        self.checkbutton.pack(side="left", fill="y")

        self.jack = jack
        self.patch_state = PatchState.IDLE

    def checkbutton_handler(self) -> None:
        self.jack.set_patch_enabled(self.checkbutton_value.get())

    def patching_callback(self, state: PatchState) -> None:
        self.patch_state = state

    def update_display(self, display_value: float) -> None:
        if self.patch_state in (PatchState.IDLE, PatchState.PATCH_ENABLED):
            if self.patch_state == PatchState.IDLE:
                intensity = 100
            else:
                intensity = 50

            if isinstance(self.jack, InputJack) and not self.jack.is_patched():
                self.set_color(0, 0, 0)
            else:
                self.set_color(
                    self.jack.color, 100, min(display_value * intensity, 100)
                )

            if self.patch_state == PatchState.PATCH_ENABLED:
                if self.jack.patch_member:
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
