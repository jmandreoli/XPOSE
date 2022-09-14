.. XPOSE documentation master file, created by
   sphinx-quickstart on Fri Feb  4 13:56:09 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

XPOSE package documentation
===========================

XPOSE is a lightweight entity management system. An **entity** is a small (few kBs), **semi-structured** piece of meta-information represented in JSON, together with a set of arbitrarily large, unstructured **attachments**. The meta-information is stored in a database called the **index** of the Xpose instance, but the structure of the meta-information is captured outside the database, as a set of JSON schemas (the **categories**). The attachments reside on a storage space, typically the file system. Each entity is characterised by its category.

The entities of an XPOSE instance can be manipulated through a REST interface.

* The back-end can easily be integrated into any HTTP server supporting CGI scripts, typically Apache httpd. Xpose access control is currently available only for the Apache server infrastructure.
* A front-end dashboard using the REST interface facilitates the management of the contents of the instance and its evolution.

Overall structure
-----------------

An Xpose instance is stored in a directory (called the **root**) containing the following members:

* an sqlite3 database (see schema below) storing the index of the instance
* the attachment directory ``attach``, with potentially one sub-directory for each entry in the index
* the category directory ``cats``, with one sub-directory for each category
* the configuration file ``config.py``, used only for instance evolution

The index database
..................

The index database has a table ``Entry`` which stores all the raw meta-information, with the following columns:

* ``oid``: entry key as an :class:`int` (primary key, auto-incremented)
* ``version``: version of this entry as an :class:`int` (always incremented on update)
* ``cat``: category of this entry as a relative path in the category directory (see below)
* ``value``: JSON encoded data for this entry, conforming to the JSON schema specified by its category
* ``attach``: relative path in the attachment directory holding the attachments of this entry
* ``created``: creation timestamp of this entry (ISO format YYYY-MM-DD[T]HH:MM:SS.ffffff)
* ``modified``: last modification timestamp of this entry (ISO format as above)
* ``access``: an access control level for this entry
* ``memo``: JSON encoded data, with no specific JSON schema (untouched by the dashboard)
* ``uid``: a permanent identifier for the entry (unlike ``oid`` which may change when the Xpose instance evolves)

.. note::
   Table ``Entry`` holds all the meta-information of the XPOSE instance. All the other tables, triggers, views, indexes etc. contain information derived from table ``Entry`` and are created and populated by the categories. This redundancy is only meant for efficiency.

One such dependent table, needed by the Xpose dashboard and other applications, is table ``Short`` with the following columns:

* ``entry``: reference to an ``Entry`` row (primary key, foreign reference)
* ``value``: short name for the entry (plain text)

Creation and Update triggers must be defined on table ``Entry`` by each category to populate table ``Short``, so that each entry has exactly one corresponding row in table ``Short``. A helper method :meth:`server.XposeServer.precompute_trigger` facilitates writing such triggers.

Categories
..........

A category name is a sequence of identifiers separated by ``/``, thus matching the structure of (posix) path names. For each category ``{cat}``, there must be a file ``cats/{cat}/schema.json`` holding a `json schema <https://json-schema.org/>`_ describing the entries of that category, and used for editing. There may also be other utility files in directory ``cats/{cat}``, e.g. `genshi templates <https://genshi.edgewall.org/>`_ producing various presentations of the entries of that category.

Furthermore, all files named ``init.py`` at any level under directory ``cats`` are executed in depth first order at the initialisation or re-initialisation of an Xpose instance. Such files may add new tables, views, triggers, indexes etc. to the index database. These in turn may populate the index database with redundant information derived from the ``Entry`` table, e.g. populating table ``Short``, required by many applications. A helper method :meth:`.server.XposeServer.precompute_trigger` is available to facilitate the definition of triggers.

Configuration
-------------

The config file must define the following variables:

* *cats* (:class:`str`): a file path to a directory containing all category specific information for the xpose instance, copied or linked (see below) as ``cats`` in the instance root
* *routes* (:class:`dict[str,XposeBase]`): a simple mapping between routes (from PATH_INFO) and corresponding resource (see below)
* *release* (:class:`int`): the latest data release
* *upgrade_{0,1,,...}* (:class:`Callable[[list[Entry]],None]`): invoked to upgrade the list of entries for each release strictly below the latest one

The dashboard makes use of the following routes (for which defaults exist):

* ``main``: for entry edition and display
* ``attach``: for attachments edition (upload, renaming, deletion)
* ``manage``: for instance-wide manipulation (evolution)

Evolution, data releases and shadowing
......................................

The (data) release of an Xpose instance refers to a version of its category structure, which may evolve over time. An Xpose instance always has a shadow instance in directory ``shadow`` (from the root). The main role of the shadow is to provide a fully functioning instance with data, categories, routes at the latest release, while the real instance still works at a possibly previous release. Once tests on the shadow are complete, its content can be synced back into the real instance. Note that attachment files are never copied between real and shadow instances (they are hard links to the same file objects). The main components of each instance are:

#. in both real and shadow instances:

   * ``index.db``: index database file
   * ``attach`` and ``attach/.uploaded``: attachment directory and sub-directory for file uploads
   * ``.routes``: routing directory containing the available (pickled) cgi resources

#. in real instance:

   * ``config.py``: symlink to readable python file containing configuration code
   * ``route.py``: generated python file which can be used as CGI script, or as target of a symbolic link CGI script
   * ``cats``: fixed snapshot copy of cats directory from config

#. in shadow instance:

   * ``cats``: symlink to cats directory from config, so that shadow always sees the latest definition of categories

Which of the real or shadow instance is served by ``route.py`` depends on a cookie ``xpose-variant``.

* When moving from real to shadow instance, the data and route directory in the shadow is replaced by that in the real instance and upgraded to its latest release. The shadow instance can be then tested. If the resulting behaviour of the shadow is not satisfactory, the problem must be fixed and the operation reiterated. The data and route directory in the real instance is untouched during this process.
* Upgrade of the real instance actually takes place when transferring from shadow to real instance, after which the two instances have the same content, and the shadow instance is ready for the next upgrade cycle.

Note that this two-phase upgrade can be performed whenever the categories change, even if the evolution does not have an impact on the categories' json schemas (ie. the release is unchanged).

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   mod_init.rst
   mod_client.rst
   mod_main.rst
   mod_server.rst
   mod_attach.rst
   mod_access.rst
   mod_initial.rst
   mod_utils.rst

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
