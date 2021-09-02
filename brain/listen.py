import socket
import sounddevice as sd
import numpy as np

def udp_loop():
    localIP = "10.0.0.2"
    localPort = 1234
    bufferSize = 1024

    msgFromServer = "I can hear you."
    bytesToSend = str.encode(msgFromServer)

    # Create a datagram socket

    UDPServerSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    UDPServerSocket.setblocking(False)

    # Bind to address and ip

    UDPServerSocket.bind((localIP, localPort))
    print("UDP server up and listening")

    # Listen for incoming datagrams

    buffer = []

    def callback(outdata, frames, time, status):
        if status:
            print(f"Sound output: {status}")

        if len(buffer) < len(outdata[:, 0]):
            # Fill as much as we can and let the rest be zero
            outdata[:len(buffer), 0] = buffer
            outdata[len(buffer):, 0].fill(0)
            buffer.clear()
        else:
            outdata[:, 0] = buffer[:len(outdata)]
            del buffer[:len(outdata)]
        # print(buffer, outdata)
        outdata *= 100

    s = sd.OutputStream(samplerate=48000, channels=1, dtype=np.int16, latency=0.30, callback=callback)
    s.start()

    while True:
        try:
            bytesAddressPair = UDPServerSocket.recvfrom(bufferSize)
        except BlockingIOError:
            continue

        message = bytesAddressPair[0]
        address = bytesAddressPair[1]

        buffer.extend(message)
        # print(buffer)

        # clientMsg = "Message from Client: {}".format(message)
        # clientIP = "Client IP Address: {}".format(address)

        # print(clientMsg)
        # print(clientIP)

        # Sending a reply to client
        # UDPServerSocket.sendto(bytesToSend, address)


if __name__ == "__main__":
    udp_loop()
