.. C.C. Cache documentation master file, created by
   sphinx-quickstart on Sun Jun 28 11:14:57 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to C.C. Cache's documentation!
======================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   core
   flask_app

`HTTP Routing Table <http-routingtable.html>`_

Basic Usage
-----------

The following curl examples show the basic flow of caching and accessing an
existing document.

.. note::

    Please make sure that the environment variables
    ``DB_INSTANCE_URI``, ``API_USERNAME`` and ``API_PASSWORD`` have been set
    properly!

.. warning::

    It is up to **you** to create a document with the ID ``argh`` in database
    ``cccache`` in advance.

Trying to fetch a document currently not in memory cache
++++++++++++++++++++++++++++++++++++++++++++++++++++++++

.. code:: bash

    curl -u user:pass -X GET --noproxy localhost http://localhost:53722/cccache/argh

.. code:: html

    <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
    <title>404 Not Found</title>
    <h1>Not Found</h1>
    <p>The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.</p>

Promoting a document to the memory cache
++++++++++++++++++++++++++++++++++++++++

.. code:: bash

    curl -u user:pass -X PUT --noproxy localhost http://localhost:53722/cccache/argh

.. code:: json

    {
      "HAL9000": "That's a very nice rendering, Dave. I think you've improved a great deal. Can you hold it a bit closer? That's Dr. Hunter, isn't it?",
      "_id": "argh",
      "_now": "2020-06-28 11:40:27",
      "_rev": "1-1543fcacaf4f2c2cdca9d5ce0b9bb611",
      "version": "1.1.1+0.ga674dfa.dirty"
    }

Fetching a document currently in memory cache
+++++++++++++++++++++++++++++++++++++++++++++

.. code:: bash

    curl -u user:pass -X GET --noproxy localhost http://localhost:53722/c/cccache/argh

.. code:: json

    {
      "HAL9000": "That's a very nice rendering, Dave. I think you've improved a great deal. Can you hold it a bit closer? That's Dr. Hunter, isn't it?",
      "_id": "argh",
      "_now": "2020-06-28 11:42:03",
      "_rev": "1-1543fcacaf4f2c2cdca9d5ce0b9bb611",
      "version": "1.1.1+0.ga674dfa.dirty"
    }

.. note::

    Please note the ``c`` for **cached** prefix. This endpoint will deliver data from memcache only, there is no fallback, cache misses will result in HTTP status 404.
    If you want fallback to storage backend retrieval use the endpoint sporting ``f`` for **fallback** prefix.

Removing a document from the memory cache
+++++++++++++++++++++++++++++++++++++++++

.. code:: bash

    curl -u user:pass -X DELETE --noproxy localhost http://localhost:53722/cccache/argh

.. code:: json

    {
      "_now": "2020-06-28 11:41:26",
      "version": "1.1.1+0.ga674dfa.dirty"
    }

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
