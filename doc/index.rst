.. brain documentation master file, created by
   sphinx-quickstart on Tue May 24 22:28:14 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to brain's documentation!
=================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

.. autoclass:: brain.Module
   :members: start, add_input, add_output, abort_all

.. autoclass:: brain.PatchState
   :members:
   :undoc-members:

.. autoclass:: brain.InputJack
   :members: is_patched, set_patch_enabled, get_data

.. autoclass:: brain.OutputJack
   :members: is_patched, set_patch_enabled, send

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
