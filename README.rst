|Build| |Status| |PyPiVersion| |License| |Downloads|

Introduction
------------

By design asyncio `does not allow <https://github.com/python/cpython/issues/66435>`_
its event loop to be nested. This presents a practical problem:
in an environment where the event loop is
already running, it's impossible to run tasks and wait
for the result. Attempting to do so will lead to a
"``RuntimeError: This event loop is already running``".

This issue pops up in various environments, including web servers,
GUI applications and in Jupyter notebooks.

This module patches asyncio to enable nested usage of ``asyncio.run`` and
``loop.run_until_complete``.

Installation
------------

.. code-block::

    pip3 install nest_asyncio

Python 3.5 or higher is required.

Usage
-----

.. code-block:: python

    from nest_asyncio import NestedAsyncIO
    with NestedAsyncIO():
        ...


Wrap any code requiring nested runs with a ``NestedAsyncIO``
context manager or manually call ``apply`` and ``revert`` on
demand. Optionally, a specific loop may be supplied as an
as argument to ``apply`` or the constructor if you do not
wish to patch the the current event loop. An event loop
may be patched regardless of its state, running
or stopped. Note that this packages is limited to ``asyncio``
event loops: general loops from other projects, such as
``uvloop`` or ``quamash``, cannot be patched.


.. |Build| image:: https://github.com/erdewit/nest_asyncio/actions/workflows/test.yml/badge.svg?branche=master
   :alt: Build
   :target: https://github.com/erdewit/nest_asyncio/actions

.. |PyPiVersion| image:: https://img.shields.io/pypi/v/nest_asyncio.svg
   :alt: PyPi
   :target: https://pypi.python.org/pypi/nest_asyncio

.. |Status| image:: https://img.shields.io/badge/status-stable-green.svg
   :alt:

.. |License| image:: https://img.shields.io/badge/license-BSD-blue.svg
   :alt:

.. |Downloads| image:: https://static.pepy.tech/badge/nest-asyncio/month
   :alt: Number of downloads
   :target: https://pepy.tech/project/nest-asyncio

