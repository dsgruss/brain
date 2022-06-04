from scipy import signal, stats
import matplotlib.pyplot as plt
import numpy as np

fs = [20 * 10 ** (x) for x in np.arange(0, 3, 0.01)]


def butter(i, j, f):
    return signal.butter(4, f, "low", False, "sos", 48000)[i, j]


for i in range(2):
    for j in range(6):
        plt.semilogx(fs, [butter(i, j, f) for f in fs])
plt.figure()


def babutter(i, j, f):
    return signal.butter(4, f, "low", False, "ba", 48000)[i][j]


for i in range(2):
    for j in range(5):
        coeff = [babutter(i, j, f) for f in fs]
        plt.semilogx(fs, coeff)
        print(i, j)
        print(
            stats.linregress(
                [np.log(f) / np.log(10) for f in fs],
                [np.log(c) / np.log(10) for c in coeff],
            )
        )
plt.figure()


def approxbabutter(i, j, f):
    return [
        [
            10 ** (3.791024027971557 * np.log(f) / np.log(10) - 16.309034199009222),
            10 ** (3.791024027971557 * np.log(f) / np.log(10) - 16.00800420334524),
            10 ** (3.791024027971557 * np.log(f) / np.log(10) - 16.309034199009222),
            1,
        ],
        [1, 2, 1, 1],
    ][i][j]


for i in range(2):
    for j in range(4):
        coeff = [approxbabutter(i, j, f) for f in fs]
        plt.loglog(fs, coeff)
plt.show()
