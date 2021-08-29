import cmd
import mido
import numpy as np
import readline
import sounddevice as sd


class Shell(cmd.Cmd):
    intro = "Welcome to the audio routing shell.   Type help or ? to list commands.\n"
    prompt = "☢️ "
    midi_inputs = {f"m{i}": d for i, d in enumerate(mido.get_input_names())}
    midi_outputs = {
        f"m{i + len(mido.get_input_names())}": d
        for i, d in enumerate(mido.get_output_names())
    }
    open_audio_devices = []
    open_midi_devices = []

    def __init__(self, api_index):
        self.api_index = api_index
        self.audio_inputs = {
            str(i): d
            for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] != 0 and d["hostapi"] == api_index
        }
        self.audio_outputs = {
            str(i): d
            for i, d in enumerate(sd.query_devices())
            if d["max_output_channels"] != 0 and d["hostapi"] == api_index
        }
        super().__init__()

    def do_list(self, arg):
        "List the attached midi and audio devices."
        if arg == "midi" or arg == "":
            print("MIDI input devices:")
            for k, v in self.midi_inputs.items():
                print(f"    {k}: {v}")
            print("MIDI output devices:")
            for k, v in self.midi_outputs.items():
                print(f"    {k}: {v}")
        if arg == "input" or arg == "":
            print("Audio input devices:")
            for k, v in self.audio_inputs.items():
                print(f"    {k}:  {v['name']}")
        if arg == "output" or arg == "":
            print("Audio output devices:")
            for k, v in self.audio_outputs.items():
                print(f"    {k}:  {v['name']}")

    def do_patch(self, arg):
        "Connect two audio devices together:  patch <input> <output>"
        if len(arg.split()) != 2:
            print("Incorrect number of parameters:  patch <input> <output>")
        inp = arg.split()[0]
        out = arg.split()[1]
        if inp not in self.midi_inputs and inp not in self.audio_inputs:
            print(f"Invalid input parameter:  {inp}")
            return
        if out not in self.midi_outputs and out not in self.audio_outputs:
            print(f"Invalid output parameter: {out}")
            return

        if inp in self.audio_inputs and out in self.audio_outputs:
            # Patch audio streams
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
            self.open_audio_devices.append(s)
        elif inp in self.midi_inputs and out in self.audio_outputs:
            # Promote midi stream to audio rate CV
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
            self.open_audio_devices.append(s)
        elif inp in self.midi_inputs and out in self.midi_outputs:
            # Midi stream direct patch
            outport = mido.open_output(self.midi_outputs[out])
            def midipass(message):
                print(message)
                outport.send(message)
            inport = mido.open_input(self.midi_inputs[inp], callback=midipass)

            self.open_midi_devices.append(outport)
            self.open_midi_devices.append(inport)
        else:
            # CV Channel downsampling
            print("CV Channel downsampling not yet implemented.")

    def do_reset(self, arg):
        "Reset all audio routing."
        while self.open_audio_devices:
            s = self.open_audio_devices.pop()
            s.stop()
            s.close()
        while self.open_midi_devices:
            self.open_midi_devices.pop().close()

    def do_exit(self, arg):
        "Close all open audio devices and exit the shell."
        self.do_reset(arg)
        exit(0)

    def do_EOF(self, arg):
        self.do_exit(arg)


def main():
    hostapis = [api['name'] for api in sd.query_hostapis()]
    for api in ['Windows WASAPI', 'MME', "Windows DirectSound"]:
        try:
            api_index = hostapis.index(api)
            break
        except ValueError:
            pass
    else:
        print("Acceptable hostapi not found.")
        exit(-1)
    Shell(api_index).cmdloop()


if __name__ == "__main__":
    main()
