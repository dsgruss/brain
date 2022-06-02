import numpy as np
import random

from brain import BLOCK_SIZE, SAMPLE_RATE

cdef class LadderFilter:
    cdef double omega0, input, pi
    cdef double state[4]
    cdef double resonance

    def __init__(self):
        self.pi = np.pi
        self.resonance = 1
        self.reset()
        self.setCutoff(0)

    def reset(self):
        for i in range(4):
            self.state[i] = 0

    cdef setCutoff(self, double cutoff):
        self.omega0 = 2 * self.pi * cutoff

    cdef process(self, double input, double dt):

        self.rk4(dt, self.state, self.input / 16000, input / 16000)
        self.input = input
        return self.state[3] * 16000

    cdef double clip(self, double x):
        if x < -3.0:
            x = -3.0
        if x > 3.0:
            x = 3.0
        return x * (27 + x * x) / (27 + 9 * x * x)

    cdef f(self, double t, double *x, double *dxdt, double input, double input_new, double dt):
        cdef double inputt = input * (t / dt) + input_new * (1 - t / dt)
        cdef double inputc = self.clip(inputt - self.resonance * x[3])
        cdef double yc0 = self.clip(x[0])
        cdef double yc1 = self.clip(x[1])
        cdef double yc2 = self.clip(x[2])
        cdef double yc3 = self.clip(x[3])

        dxdt[0] = self.omega0 * (inputc - yc0)
        dxdt[1] = self.omega0 * (yc0 - yc1)
        dxdt[2] = self.omega0 * (yc1 - yc2)
        dxdt[3] = self.omega0 * (yc2 - yc3)

    cdef rk4(self, double dt, double *x, double input, double input_new):
        cdef double yi[4]
        cdef double k1[4]
        cdef double k2[4]
        cdef double k3[4]
        cdef double k4[4]

        self.f(0, x, k1, input, input_new, dt)
        for i in range(4):
            yi[i] = x[i] + k1[i] * dt / 2
        self.f(dt / 2, yi, k2, input, input_new, dt)
        for i in range(4):
            yi[i] = x[i] + k2[i] * dt / 2
        self.f(dt / 2, yi, k3, input, input_new, dt)
        for i in range(4):
            yi[i] = x[i] + k3[i] * dt
        self.f(dt, yi, k4, input, input_new, dt)
        for i in range(4):
            x[i] += dt * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) / 6

    def block_process(self, double[:] input, double filter_freq, double resonance):
        cdef int block_size = BLOCK_SIZE

        result = np.zeros((BLOCK_SIZE, ), dtype=np.double)
        cdef double[:] result_view = result
        for j in range(block_size):
            self.setCutoff(filter_freq)
            self.resonance = resonance
            result_view[j] = self.process(input[j] + 1e-6 * random.random(), 1 / SAMPLE_RATE)
        return result
