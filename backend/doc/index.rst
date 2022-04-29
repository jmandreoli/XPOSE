.. XPOSE documentation master file, created by
   sphinx-quickstart on Fri Feb  4 13:56:09 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

XPOSE package documentation
===========================

XPOSE is a lightweight entity management system. An **entity** is a small (~10K), structured piece of meta-information represented in JSON, together with a set of arbitrary **attachments**. The meta information is stored in a database called the **index** of the Xpose instance, while the attachments reside on the file system. Each entity is characterised by its **category**, which specifies how it can be manipulated (edited, converted to various presentation formats, etc.).

Overall structure
-----------------

An Xpose instance is stored in a directory (called the **root**) containing the following members:

* an sqlite3 database (see schema below) storing the index of the instance
* the attachment directory with potentially one sub-directory for each entry in the index
* the category directory, with one sub-directory for each category, holding manipulation information

The index database has a table ``Entry`` which stores all the raw meta-information, with the following columns:

* ``oid``: entry key as an :class:`int` (primary key, auto-incremented)
* ``version``: version of this entry as an :class:`int` (always incremented on update)
* ``cat``: category as a relative path in the ``cats`` directory (see below)
* ``value``: JSON encoded data, conforming to the JSON schema of the category held by ``cat``
* ``attach``: relative path in the ``attach`` directory holding the attachments of this entry
* ``created``: creation timestamp of this entry in ISO format YYYY-MM-DD[T]HH:MM:SS.ffffff
* ``modified``: last modification timestamp of this entry in same format as ``created``
* ``access``: an access control level for this entry
* ``memo``: JSON encoded data, with no specific JSON schema (untouched by the dashboard)

Note that field ``created`` is unique for each entry and can be used as permanent identifier (unlike ``oid`` which may change when the Xpose instance is re-initialised).

All the other tables, triggers, views, indexes etc. contain information derived from table ``Entity`` and are created and populated by the categories. One such dependent table, needed by hte dashboard, is table ``Short`` with the following columns:

* ``entry``: reference to an ``Entry`` row (primary key, foreign reference)
* ``value``: short name for the entry (plain text)

Creation and Update triggers on table ``Entry`` must be defined in each category to populate table ``Short``, so that each entity has exactly one corresponding row in table ``Short``.

The following sqlite functions are made available in the index database in contexts where they are needed:

* ``create_attach`` *oid* -> *attach*: maps the *oid* field to the *attach* fields of an entry
* ``delete_attach`` *oid* ->: called when an entry with a given *oid* field is deleted
* ``authorise`` *level* -> *yes-no*: maps an access *level* to a *yes-no* boolean indicating whether access is granted at that level, given credentials from the context
* ``authoriser`` *level*, *path* ->: sets the access control to *path* to the given *level*
* ``apply_template`` *tmpl*, *err_tmpl*, *rendering*, *args* ->: applies a genshi template *tmpl* rendered as *rendering* with arguments *args*; in case of error, applies template *err_tmpl* instead

Categories
----------

A category name is a sequence of identifiers separated by ``/``, thus matching the structure of (posix) path names. For each category ``{cat}``, there must be a file ``cats/{cat}/schema.json`` holding a `json schema <https://json-schema.org/>`_ describing the entries of that category, and used for editing. There may also be other utility files in directory ``cats/{cat}``, e.g. `genshi templates <https://genshi.edgewall.org/>`_ producing various presentations of the entries of that category.

Furthermore, all files named ``init.py`` at any level under directory ``cat`` are executed in depth first order at the initialisation or re-initialisation of an Xpose instance. Such files may add new tables, views, triggers, indexes etc. to the index database. These in turn may populate the index database with redundant information derived from the ``Entry`` table, e.g. populating table ``Short``, required by many applications. The main principle is that all the information of an Xpose instance is entirely contained in the ``Entry`` table as well as the attachment directory, so that a whole Xpose instance can be copied, moved around or upgraded by just preserving these two components. A helper method :meth:`.server.XposeServer.precompute_trigger` is available to facilitate the definition of triggers.

Configuration file
------------------

The config file must define the following variables:

* *cats* (:class:`str`): a file path to a directory containing all the meta information (categories) of the xpose instance
* *routes* (:class:`dict[str,XposeBase]`): a simple mapping between routes (from PATH_INFO) and corresponding resource (defaults exist for ``main``, ``attach``, and ``manage``)
* *release* (:class:`int`): the latest data release
* *upgrade_{0,1,,...}* (:class:`Callable[[list[Entry]],None]`): invoked to upgrade the list of entries for each release strictly below the latest one

Evolution, data releases and shadowing
--------------------------------------

The (data) release of an Xpose instance refers to a version of its category schemas, which may evolve over time. An Xpose instance always has a shadow instance in directory ``shadow`` (from the root). The main role of the shadow is to provide a fully functioning instance with data, categories, routes at the latest release, while the real instance still works at a previous release. Once tests on the shadow are complete, its content can be copied back into the real instance. Note that attachment files are never copied between real and shadow instances (they are hard links to the same file objects). The main components of each instance are:

#. in both real and shadow instances:

   * ``index.db``: index database file
   * ``attach`` and ``attach/.uploaded``: attachment directory and sub-directory for file uploads
   * ``.routes``: routing directory containing release specific configured manipulation scripts

#. in real instance:

   * ``config.py``: symlink to readable python file containing configuration code (see below)
   * ``route.py``: generated python file which can be used as CGI script, or as target of a symbolic link CGI script
   * ``cats``: fixed snapshot copy of cats directory from config

#. in shadow instance:

   * ``cats``: symlink to cats directory from config, so that shadow always sees the latest definition of categories

Which of the real or shadow instance is served by ``route.py`` depends on a cookie ``xpose-variant``.

* When moving from real to shadow instance, the data and route directory in the shadow is replaced by that in the real instance and upgraded to its latest release. If the resulting behaviour of the shadow is not satisfactory, the problem must be fixed and the operation reiterated. The data and route directory in the real instance is untouched during this process.
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
