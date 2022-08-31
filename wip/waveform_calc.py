import numpy as np
import matplotlib.pyplot as plt

def saw(phase):
    return -1 + (phase % 1) * 2

def tri(phase):
    phase = phase % 1
    if phase < 0.5:
        return -1 + 4 * phase
    else:
        return 1 - 4 * (phase - 0.5)

ts = np.arange(0, 4, 0.01)
s0 = [saw(t) for t in ts]
s1 = [saw(t + 0.5) for t in ts]
s2 = [saw(t) - saw(t + 0.25) for t in ts]  # Square wave with duty cycle 0.25
s3 = [tri(t) for t in ts]
s4 = [0.75 * tri(t) + 0.25 * saw(t) for t in ts]

# plt.plot(ts, s0)
# plt.plot(ts, s1)
plt.plot(ts, s4)
plt.show()
