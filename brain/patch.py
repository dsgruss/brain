import cmd
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

    open_audio_devices = []
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
        "List the attached audio devices and discovered ethernet devices."
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
                print(f"    {k}: {v['device']} - {v['name']} @ {v['addr']}")
            print("Ethernet audio outputs:")
            for k, v in self.eth_outputs.items():
                print(f"    {k}: {v['device']} - {v['name']} @ {v['addr']}:{v['port']}")

    def do_patch(self, arg):
        "Connect two audio devices together:  patch <input> <output>"
        if len(arg.split()) != 2:
            print("Incorrect number of parameters:  patch <input> <output>")
        inp = arg.split()[0]
        out = arg.split()[1]
        if (
            inp not in self.audio_inputs
            and inp not in self.eth_inputs
        ):
            print(f"Invalid input parameter:  {inp}")
            return
        if (
            out not in self.audio_outputs
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
            buffersize = 2
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
                    print("\nBuffer is empty: increase buffersize?")
                    outdata[:] = np.zeros(outdata.shape)
                    return
                # assert len(data) == len(outdata)
                res = np.frombuffer(data, dtype=np.int16).reshape((frames, 8))
                outdata[:, 0] = sum(res[:, i] / 4 for i in range(8))

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
        elif inp in self.eth_inputs and out in self.eth_outputs:
            # Send a control message to link two devices
            dev_in = self.eth_inputs[inp]
            dev_out = self.eth_outputs[out]

            control_sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
            control_sock.sendto(
                b"REQUEST   "
                + socket.inet_aton(dev_out["addr"])
                + int.to_bytes(dev_out["port"], 2, "big")
                + int.to_bytes(dev_in["id"], 1, "big"),
                (dev_in["addr"], 10000),
            )
            control_sock.close()
        else:
            print("Not yet implemented.")

    def do_reset(self, arg):
        "Reset all audio routing."
        while self.open_audio_devices:
            s = self.open_audio_devices.pop()
            s.stop()
            s.close()

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
        sock.bind((interface["addr"], 12525))
        sock.settimeout(1)
        sock.sendto(b"IDENTIFY", (interface["broadcast"], 10000))
        while True:
            try:
                msg, addr = sock.recvfrom(1500)
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
