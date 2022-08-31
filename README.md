Current Status - Deprecated
---------------------------

This project was a very early work-in-progress alpha, which means that the interfaces, the
communication protocols, and general design has not yet been finalized (some of these outright do
not work in their current state). Python has allowed for rapid prototyping and iteration, but has
since shifted away for the following reasons:

- The primary reason is the maintenance of two different software stacks: one for developing and
  testing on the PC and another for actual hardware code. Since this was experimental in a lot of
  ways, changes had to be synchronized and propagated between them. This applied to both the base
  protocols as well as specific implementations of modules. This was essentially twice as much work
  for not much benefit past the initial stage. Going forward, everything past the UI layer will run
  common code and working prototypes can be deployed to hardware in a rapid fashion. Since the
  project is primarily network-based, making sure that data is handled identically between different
  variants is critical.

- Although certain parts can be written to execute quickly in python (see the filter in the example
  or times that numpy was used), usually making things performant enough for audio applications
  would require yet another rewrite of critical code. This again began to drag on development
  efforts and is especially unfortunate in the cases where only a small experiment or test is
  needed. Along these lines, some libraries are written without an expectation of performance.

- Lastly, this section of the project was initially built for the purpose of finding out if such a
  thing would actually work, and what potential pitfalls await, and would likely need much of a
  rewrite to sand off the rough edges and make the library generically useful.

This repository will remain as historical reference and for quick testing/prototyping.

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
