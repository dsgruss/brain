Introduction
------------

This project is part of an experiment in creating a
[polyphonic](https://en.wikipedia.org/wiki/Polyphony) version of a [modular
synthesizer](https://en.wikipedia.org/wiki/Modular_synthesizer) using ethernet communication. The
high-level goal is to determine if maintaining low-latency (~1 ms per module) high-throughput (8
parallel channels of uncompressed audio) communication is possible on consumer-level networking
hardware and low-cost microcontrollers.

This subproject in particular contains python implementations of the control system shell and
prototype software modules. This is more or less used as a "staging ground" for different module and
protocol concepts before committing them to microcontroller code and physical hardware.

The primary interface to the library is in the `brain.Module` object, which mediates all of the
patching and dataflow between all other modules on the network. Typically, a module only needs to be
written as a processor on the input state to the output state and handle the associated user
interface.

Installation
------------

Setting up the project requires a python 3 interpreter with [poetry](https://python-poetry.org/)
installed to manage dependencies. Use 

    poetry install

to create the virtual environment and install all the requirements and then

    poetry shell

to spawn a shell with that environment. `build.bat` provides some basic formatting and building,
although it shouldn't be needed unless using it with specific examples. Examples are found in the
`examples` directory, with `manager.py` being used to spawn other example subprocesses. `honcho
start` can also be used to launch a variety of different example modules.

Current Status
--------------

This project is currently a very early work-in-progress alpha, which means that any and all
interfaces may change, the communication protocols are still in flux, and it has not been completely
tested to work in all environments. Consider it more of an proof-of-concept experiment than a
completed library.

Todo
----

- [ ] Move broadcasts to multicast (and find a way to test locally)
- [ ] Add consensus algorithm for patch states
- [ ] Add state capture and restore
- [ ] Add heartbeats for patch status and for global patch updates
- [ ] Change from build script to actual build process
- [ ] Come up with a better name
