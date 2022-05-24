import colorsys
import tkinter as tk

from brain import Jack


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

    def checkbutton_handler(self):
        self.jack.set_patch_enabled(self.checkbutton_value.get())

    def set_color(self, hue: int, saturation: int, value: int):
        """hue -> 0, 359; saturation -> 0, 100; value -> 0, 100"""
        r, g, b = colorsys.hsv_to_rgb(hue / 360, saturation / 100, value / 100)
        r = int(r * 255)
        g = int(g * 255)
        b = int(b * 255)
        color = f"#{r:02x}{g:02x}{b:02x}"
        self.light.delete("light")
        self.light.create_oval(5, 5, 20, 20, fill=color, tags="light")
