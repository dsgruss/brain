import tkinter as tk

from brain import module


class tkJack(tk.Checkbutton):
    """tk display widget for an input or output jack"""

    def __init__(self, parent: tk.Tk, jack: module.Jack, text: str) -> None:
        self.checkbutton_value = tk.BooleanVar()
        self.jack = jack

        super().__init__(
            master=parent,
            text=text,
            variable=self.checkbutton_value,
            command=self.checkbutton_handler,
        )

    def checkbutton_handler(self):
        self.jack.set_patch_enabled(self.checkbutton_value.get())
