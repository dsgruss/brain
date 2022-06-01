from distutils.core import setup
from Cython.Build import cythonize

setup(name="Basic Filter", ext_modules=cythonize("filter_core.pyx", annotate=True))
