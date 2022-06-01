import numpy as np

from brain import BLOCK_SIZE, SAMPLE_RATE

cdef class LadderFilter:
    cdef double omega0, state[4], input, input_new, dt, pi

    def __init__(self):
        self.pi = np.pi
        self.reset()
        self.setCutoff(0)

    def reset(self):
        for i in range(4):
            self.state[i] = 0

    cdef setCutoff(self, double cutoff):
        self.omega0 = 2 * self.pi * cutoff

    cdef process(self, double input, double dt):

        self.input_new = input
        self.dt = dt
        self.rk4(dt, self.state)
        self.input = input
        return self.state[3]

    cdef rk4(self, double dt, double *x):
        cdef double yi[4], k1[4], k2[4], k3[4], k4[4]

        # f(0, x, k1)
        k1[0] = self.omega0 * (self.input - x[0])
        k1[1] = self.omega0 * (x[0] - x[1])
        k1[2] = self.omega0 * (x[1] - x[2])
        k1[3] = self.omega0 * (x[2] - x[3])
        for i in range(4):
            yi[i] = x[i] + k1[i] * dt / 2
        # f(dt / 2, yi, k2)
        k2[0] = self.omega0 * ((self.input + self.input_new) / 2 - yi[0])
        k2[2] = self.omega0 * (yi[1] - yi[2])
        k2[1] = self.omega0 * (yi[0] - yi[1])
        k2[3] = self.omega0 * (yi[2] - yi[3])
        for i in range(4):
            yi[i] = x[i] + k2[i] * dt / 2
        # f(dt / 2, yi, k3)
        k3[0] = self.omega0 * ((self.input + self.input_new) / 2 - yi[0])
        k3[2] = self.omega0 * (yi[1] - yi[2])
        k3[1] = self.omega0 * (yi[0] - yi[1])
        k3[3] = self.omega0 * (yi[2] - yi[3])
        for i in range(4):
            yi[i] = x[i] + k3[i] * dt
        # f(dt, yi, k4)
        k4[0] = self.omega0 * (self.input_new - yi[0])
        k4[2] = self.omega0 * (yi[1] - yi[2])
        k4[1] = self.omega0 * (yi[0] - yi[1])
        k4[3] = self.omega0 * (yi[2] - yi[3])
        for i in range(4):
            x[i] += dt * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) / 6

    def block_process(self, double[:] input, double filter_freq):
        cdef int block_size = BLOCK_SIZE

        result = np.zeros((BLOCK_SIZE, ), dtype=np.double)
        cdef double[:] result_view = result
        for j in range(block_size):
            self.setCutoff(filter_freq)
            result_view[j] = self.process(input[j], 1 / SAMPLE_RATE)
        return result
