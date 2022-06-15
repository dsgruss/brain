Data Format
===========

In modular, communication is done using mostly unstructured
voltages. Usually, it is up to the operator to manage what differing
values mean, with the end result being an audio signal. However, there
are some common practices for different data types that end up
more-or-less as a standard.

Similarly, in this project, the core data type is an unstructured data
frame that each module can process in arbitrary ways. This document
also defines a few conventions for how to use different signals, but
they are by no means required.

Audio Rate Signal Basics
------------------------

Each input and output jack is responsible for creating or consuming an
eight channel, 16-bit signal at an audio rate of 48,000 samples per
second. This signal is broken up into blocks of one millisecond in
length or 48 samples per channel. These samples are in "C-style"
order, so the channels are interwoven for each sample::

          Channel 1           Channel 0, Sample 1
              |                     |
            -----                 -----
      00 01 FF FF 20 20 ... 12 34 00 01 ...
      -----                 -----
        |                     |
  Channel 0, Sample 0     Channel 7

Each 16-bit value is a signed int, so the zero-volts equivalent is
just ``00 00``. Each one of these blocks is sent as a single UDP packet at
the same rate of one per millisecond.

This audio rate condition is forced on all modules, even those that
don't necessarily require it (such as envelope generators). This is to
ensure that all modules work within the given constraints, and to
defer decisions about interpolation or value stepping to module that
actually generated the signal.

All signal are uncompressed audio, so each stream takes up
approximately 8 Mb/s of bandwidth. This is to eliminate as much latency
as possible associated with compressing and decompressing blocks of
data. To that end, output signals should be created as fast as
possible after receiving the input signal, with the target being a
double-buffer between getting data and creating new data. Any latency
in the system can potentially impact timing of triggers and gates and
can also make it difficult to play as a live instrument.

Finally, this bandwidth use means that there is a budget of about 15
input jacks and 15 output jacks to use on the module, but this could
be extended using additional Ethernet connections for particularly
large models.

V/Oct
-----

For pitch information, any sort of exponential conversion to Hz would
potentially work. However, like the V/Oct standard, it is useful to
have a common scale so that tuning is maintained. Since we are working
with a digital format, we can go one further and specify an exact
pitch for a given note.

The top seven bits correspond to the MIDI note value, with zero being
MIDI note 69 or a concert A. The remaining nine bits are fractions of
a note. Therefore, the conversion from a V/Oct signal to Hz is::

  frequency = 440 * 2 ^ (v_oct / (512 * 12))

This is about 5 cents difference per bit around 440 Hz.

Gates and Triggers
------------------

Generally, signals are unipolar, with zero being "off" and a value
greater than ``2 ^ 10`` being "on" (that is, it can be checked by
examining the high bits). Sometimes, it is useful to have a tri-state
signal (for instance for signaling an envelope to close rather than go
to a release stage), in which case the ``-2 ^ 10`` value is used.

Again, this is using quite a lot of data for such a simple signal, but
it allows the user to mix and match sources without needing to be
concerned if the downstream module can handle the data or not.
