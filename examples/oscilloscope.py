from brain import module

class Oscilloscpe:
    # Utility for monitoring module outputs

    def __init__(self):
        self.module_interface = module.Module()
        self.input = self.module_interface.add_input(self.data_callback)

    def patching_callback(self, id):
        if not self.input.is_patched():
            self.module_interface.accept_patch(id)

    def data_callback(self, data: bytes):
        print(bytes)

if __name__ == "__main__":
    app = Oscilloscpe()