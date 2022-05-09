:mod:`XPOSE.initial` --- initialisation
=======================================

To initialise an Xpose instance, run the command::

   PYTHONPATH=<path-to-xpose-package> <python-exe> -m xpose.initial <arguments>

where

* the ``PYTHONPATH`` enviroment variable must give access to the XPOSE package
* the resulting cgi-script will use the same python executable as specified in the command
* the meaning of the arguments can be obtained by passing option ``-h`` or ``--help``

The command above assumes the name of the XPOSE package is xpose (default). It may be changed, in which case it must be changed in the ``-m`` option above, and must also be explicitly provided with option ``-x``.

.. automodule:: XPOSE.initial
   :members:
   :member-order: bysource
   :show-inheritance:
