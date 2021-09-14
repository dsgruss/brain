import cmd
import mido
import numpy as np
import readline
import sounddevice as sd
import socket
import threading
import queue
import netifaces
import json

from operator import itemgetter


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
    eth_inputs = {}
    eth_outputs = {}
    open_udp_sockets = []
    active_threads = []

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
        if arg == "eth" or arg == "":
            print("Ethernet audio inputs:")
            for k, v in self.eth_inputs.items():
                print(f"    {k}: {v}")
            print("Ethernet audio outputs:")
            for k, v in self.eth_outputs.items():
                print(f"    {k}: {v}")

    def do_patch(self, arg):
        "Connect two audio devices together:  patch <input> <output>"
        if len(arg.split()) != 2:
            print("Incorrect number of parameters:  patch <input> <output>")
        inp = arg.split()[0]
        out = arg.split()[1]
        if (
            inp not in self.midi_inputs
            and inp not in self.audio_inputs
            and inp not in self.eth_inputs
        ):
            print(f"Invalid input parameter:  {inp}")
            return
        if (
            out not in self.midi_outputs
            and out not in self.audio_outputs
            and out not in self.eth_outputs
        ):
            print(f"Invalid output parameter: {out}")
            return

        if inp in self.audio_inputs and out in self.audio_outputs:
            # Patch audio streams
            def passcallback(indata, outdata, frames, time, status):
                if status:
                    print(f"\nPassthrough: {status}")
                _, inChannels = indata.shape
                _, outChannels = outdata.shape
                if inChannels == outChannels:
                    outdata[:] = indata
                elif outChannels == 2:
                    # Perform a mixdown for monitoring
                    outdata[:] = np.zeros(outdata.shape)
                    for i in range(inChannels):
                        outdata[:, 0] += indata[:, i] / inChannels
                        outdata[:, 1] += indata[:, i] / inChannels
                elif inChannels < outChannels:
                    outdata[:, :inChannels] = indata
                else:
                    print(
                        f"\nInconsistent channel sizes: in {inChannels}, out {outChannels}"
                    )

            s = sd.Stream(
                device=(int(inp), int(out)),
                samplerate=48000,
                latency=0.030,
                callback=passcallback,
            )

            s.start()
            self.open_audio_devices.append(s)
        elif inp in self.midi_inputs and out in self.audio_outputs:
            # Promote midi stream to audio rate CV (incomplete)
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
        elif inp in self.midi_inputs and out in self.eth_outputs:
            # Promote midi stream to audio rate CV, streaming over ethernet
            channels = 8
            timestamp = [0]

            voices = [{"note": 0, "on": False, "timestamp": 0} for _ in range(channels)]

            def midi_to_cv_callback(message: mido.Message):
                timestamp[0] += 1
                if message.type == "note_off":
                    for v in voices:
                        if v["note"] == message.note and v["on"]:
                            v["on"] = False
                            v["timestamp"] = timestamp[0]
                elif message.type == "note_on":
                    # First see if we can take the oldest voice that has been released
                    voices_off = sorted(
                        (v for v in voices if v["on"] == False),
                        key=itemgetter("timestamp"),
                    )
                    if len(voices_off) > 0:
                        voices_off[0]["note"] = message.note
                        voices_off[0]["on"] = True
                        voices_off[0]["timestamp"] = timestamp[0]
                    else:
                        # Otherwise, steal a voice. In this case, take the oldest note played. We
                        # also have a choice of whether to just change the pitch (done here), or to
                        # shut the note off and retrigger.
                        voice_steal = sorted(
                            (v for v in voices), key=itemgetter("timestamp")
                        )[0]
                        voice_steal["note"] = message.note
                        voice_steal["timestamp"] = timestamp[0]
                for v in voices:
                    print(v)
                print()

            inport = mido.open_input(
                self.midi_inputs[inp], callback=midi_to_cv_callback
            )
            self.open_midi_devices.append(inport)
        elif inp in self.midi_inputs and out in self.midi_outputs:
            # Midi stream direct patch
            outport = mido.open_output(self.midi_outputs[out])

            def midipass(message):
                # print(message)
                outport.send(message)

            inport = mido.open_input(self.midi_inputs[inp], callback=midipass)

            self.open_midi_devices.append(outport)
            self.open_midi_devices.append(inport)
        elif inp in self.audio_inputs and out in self.eth_outputs:
            # Audio device to ethernet stream routing

            sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
            sock.setblocking(False)

            def audio_eth_callback(indata, frames, t, status):
                if status:
                    print(f"Audio -> Ethernet: {status}")
                rtp_header = bytes("############", "ASCII")
                audio_data = np.zeros((48, 8), dtype=np.int16)
                for i in range(0, len(indata[:, 0]), 48):
                    audio_data[:, 0] = indata[i : (i + 48), 0]
                    sock.sendto(
                        rtp_header + audio_data.tobytes(),
                        (self.eth_outputs[out]["addr"], self.eth_outputs[out]["port"]),
                    )

            s = sd.InputStream(
                device=int(inp),
                samplerate=48000,
                channels=1,
                dtype=np.int16,
                latency=0.030,
                callback=audio_eth_callback,
            )
            s.start()
            self.open_audio_devices.append(s)
        elif inp in self.eth_inputs and out in self.audio_outputs:
            # Ethernet stream to audio device routing

            blocksize = 960
            buffersize = 5
            samplerate = 48000
            q = queue.Queue(maxsize=buffersize)

            def recv_thread():
                dev = self.eth_inputs[inp]
                sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
                sock.bind((dev["local_addr"], 12000))

                control_sock = socket.socket(
                    family=socket.AF_INET, type=socket.SOCK_DGRAM
                )
                control_sock.sendto(
                    b"REQUEST   "
                    + socket.inet_aton(dev["local_addr"])
                    + int.to_bytes(12000, 2, "big")
                    + int.to_bytes(dev["id"], 1, "big"),
                    (dev["addr"], 10000),
                )
                control_sock.close()

                outbuffer = bytes()

                while True:
                    msg, addr = sock.recvfrom(12 + 8 * 48 * 2)
                    outbuffer += msg[12:]
                    if len(outbuffer) == blocksize * 2 * 8:
                        q.put(outbuffer)
                        outbuffer = bytes()

            def audio_in_eth_callback(outdata, frames, time, status):
                assert frames == blocksize
                if status.output_underflow:
                    print("Output underflow: increase blocksize?")
                    raise sd.CallbackAbort
                assert not status
                try:
                    data = q.get_nowait()
                except queue.Empty as e:
                    print("Buffer is empty: increase buffersize?")
                    raise sd.CallbackAbort from e
                # assert len(data) == len(outdata)
                outdata[:, 0] = np.frombuffer(data, dtype=np.int16).reshape(
                    (frames, 8)
                )[:, 0]

            s = sd.OutputStream(
                device=int(out),
                samplerate=samplerate,
                channels=1,
                dtype=np.int16,
                blocksize=blocksize,
                callback=audio_in_eth_callback,
            )

            self.open_audio_devices.append(s)

            threading.Thread(target=recv_thread, daemon=True).start()
            while not q.full():
                pass
            s.start()
        else:
            print("Not yet implemented.")

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
    hostapis = [api["name"] for api in sd.query_hostapis()]
    for api in ["Windows WASAPI", "MME", "Windows DirectSound"]:
        try:
            api_index = hostapis.index(api)
            break
        except ValueError:
            pass
    else:
        print("Acceptable hostapi not found.")
        exit(-1)
    s = Shell(api_index)
    print("Discovering network interfaces...")
    interfaces = []
    for interface in netifaces.interfaces():
        interfaces_details = netifaces.ifaddresses(interface)
        if netifaces.AF_INET in interfaces_details:
            interfaces.extend(interfaces_details[netifaces.AF_INET])
    # print(interfaces)
    print("Discovering devices...")
    identifier = 0
    for interface in interfaces:
        print(f"Querying on {interface['addr']}")
        sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        sock.bind((interface["addr"], 10000))
        sock.settimeout(1)
        sock.sendto(b"IDENTIFY", (interface["broadcast"], 10000))
        while True:
            try:
                msg, addr = sock.recvfrom(512)
                if msg.startswith(b"IDENTIFY"):
                    continue
                res = json.loads(msg)
                print(f"Got response from {addr}: {res}")
                for v in res["inputs"]:
                    v["addr"] = addr[0]
                    v["device"] = res["name"]
                    v["local_addr"] = interface["addr"]
                    s.eth_outputs["e" + str(identifier)] = v
                    identifier += 1
                for v in res["outputs"]:
                    v["addr"] = addr[0]
                    v["device"] = res["name"]
                    v["local_addr"] = interface["addr"]
                    s.eth_inputs["e" + str(identifier)] = v
                    identifier += 1
            except socket.timeout:
                break
        sock.close()
    s.cmdloop()


if __name__ == "__main__":
    main()
