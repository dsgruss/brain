import mido
import sounddevice as sd
import numpy as np


def main():

    inmidi = mido.get_input_names()
    defmidi = 1 if len(inmidi) > 1 else 0

    for i, dev in enumerate(inmidi):
        print(f"{i}: {dev}")

    resp = input(f"Select midi device [{defmidi}]: ")
    if resp == "":
        resp = defmidi
    else:
        resp = int(resp)

    audio = sd.query_devices()
    outputs = [(i, d) for i, d in enumerate(audio) if d["max_output_channels"] != 0]
    if len(outputs) == 0:
        print("No output devices found")
        exit(1)
    print()
    print(audio)
    respout = input(f"Select output device [8]: ")
    if respout == "":
        respout = 8
    else:
        respout = int(respout)
    print(audio[respout]["name"])

    promptout = [
        i
        for i, d in enumerate(audio)
        if "Prompt" in d["name"] and d["max_input_channels"] != 0
    ]
    promptcv = [
        i
        for i, d in enumerate(audio)
        if "Prompt" in d["name"] and d["max_output_channels"] != 0
    ]
    if len(promptcv) == 0 or len(promptout) == 0:
        print("Board not detected")
        exit(1)

    input(f"Found device at {promptcv[0]} and {promptout[0]} [confirm]: ")

    onnotes = set()
    pw = [0]

    def print_message(msg):
        print(msg)
        if msg.type == "note_on":
            onnotes.add(msg.note)
        elif msg.type == "note_off":
            onnotes.discard(msg.note)
        elif msg.type == "pitchwheel":
            pw[0] = msg.pitch
        print(msg, onnotes)

    def passcallback(indata, outdata, frames, time, status):
        if status:
            print(f"Passthrough: {status}")
        outdata[:, 0] = indata[:, 0]
        outdata[:, 1] = indata[:, 0]

    pitchval = [0]

    def callback(outdata, frames, time, status):
        if status:
            print(f"CV Send: {status}")
        if len(onnotes) == 0:
            outdata[:, 1].fill(0)
        else:
            pitchval[0] = max(onnotes) * 256
            outdata[:, 1].fill(16000)
        outdata[:, 0].fill(pitchval[0] + pw[0] / 32)

    with sd.OutputStream(
        device=promptcv[0],
        samplerate=48000,
        channels=2,
        dtype=np.int16,
        latency=0.030,
        callback=callback,
    ):
        with sd.Stream(
            device=(promptout[0], respout),
            samplerate=48000,
            channels=2,
            latency=0.030,
            callback=passcallback,
        ):
            with mido.open_input(inmidi[resp], callback=print_message):
                input("end ")


if __name__ == "__main__":
    main()
