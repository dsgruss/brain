import cmd
import mido
import numpy as np
import readline
import sounddevice as sd


class Shell(cmd.Cmd):
    intro = 'Welcome to the audio routing shell.   Type help or ? to list commands.\n'
    prompt = '☢️ '
    inputs = {str(i): d for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] != 0 and d['hostapi'] == 0}
    outputs = {str(i): d for i, d in enumerate(sd.query_devices()) if d["max_output_channels"] != 0 and d['hostapi'] == 0}
    inmidi = {f"m{i}": d for i, d in enumerate(mido.get_input_names()) }
    outmidi = {f"m{i + len(mido.get_input_names())}": d for i, d in enumerate(mido.get_output_names()) }
    open_devices = []

    def do_list(self, arg):
        'List the attached midi and audio devices.'
        if arg == "midi" or arg == "":
            print("MIDI input devices:")
            for k, v in self.inmidi.items():
                print(f"    {k}: {v}")
            print("MIDI output devices:")
            for k, v in self.outmidi.items():
                print(f"    {k}: {v}")
        if arg == "input" or arg =="":
            print("Audio input devices:")
            for k, v in self.inputs.items():
                print(f"    {k}:  {v['name']}")
        if arg == "output" or arg =="":
            print("Audio output devices:")
            for k, v in self.outputs.items():
                print(f"    {k}:  {v['name']}")

    def do_patch(self, arg):
        'Connect two audio devices together:  patch <input> <output>'
        if len(arg.split()) != 2:
            print("Incorrect number of parameters:  patch <input> <output>")
        inp = arg.split()[0]
        out = arg.split()[1]
        if inp not in self.inmidi and inp not in self.inputs:
            print(f"Invalid input parameter:  {inp}")
            return
        if out not in self.outputs:
            print(f"Invalid output parameter: {out}")
            return

        if inp in self.inputs:
            def passcallback(indata, outdata, frames, time, status):
                if status:
                    print(f"\nPassthrough: {status}")
                outdata[:] = indata

            s = sd.Stream(
                device=(int(inp), int(out)),
                samplerate=48000,
                channels=2,
                latency=0.030,
                callback=passcallback,
            )

            s.start()
            self.open_devices.append(s)
        else:
            def callback(outdata, frames, time, status):
                if status:
                    print(f"CV Send: {status}")
                
                # msg.pitch (note) * 256 + msg.pitch (pitchwheel) / 32
                outdata[:, 0].fill(50 * 256)
                outdata[:, 1].fill(16000)

            s = sd.OutputStream(
                device=int(out),
                samplerate=48000,
                channels=2,
                dtype=np.int16,
                latency=0.030,
                callback=callback,
            )

            s.start()
            self.open_devices.append(s)

    def do_reset(self, arg):
        'Reset all audio routing.'
        while self.open_devices:
            s = self.open_devices.pop()
            s.stop()
            s.close()

    def do_exit(self, arg):
        'Close all open audio devices and exit the shell.'
        self.do_reset(arg)
        exit(0)

    def do_EOF(self, arg):
        self.do_exit(arg)

def main():
    Shell().cmdloop()

if __name__ == "__main__":
    main()
