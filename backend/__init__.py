# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: a JSON database manager (server side)
#

r"""
:mod:`xpose` --- A JSON database manager
========================================

An Xpose instance is a directory (root) containing the following members:

* ``index.db``: an sqlite3 database (see schema below), called the index of the instance
* ``attach``: the attachment folder with potentially one subfolder for each entry in the index
* ``attach/.uploaded``: a folder for temporary file uploads
* ``cats``: the category folder holding all the information related to the entry categories

The index database has the following tables:

#. Table ``Entry`` with fields

   * ``oid``: entry key as an :class:`int` (primary key, auto-incremented)
   * ``version``: version of the entry as an :class:`int` (always incremented on update)
   * ``cat``: category as a relative path in the ``cats`` folder (see below)
   * ``value``: JSON encoded data, conforming to the JSON schema of the category held by ``cat``
   * ``attach``: relative path in the ``attach`` folder holding the attachments of this entry
   * ``created``: creation timestamp of this entry in ISO format YYYY-MM-DD[T]HH:MM:SS
   * ``modified``: last modification timestamp of this entry in same format as ``created``
   * ``access``: an access control key for this entry
   * ``memo``: JSON encoded data, with no specific JSON schema, and never touched by Xpose (for use by other applications)

#. Table ``Short`` with fields

   * ``entry``: reference to an ``Entry`` row (primary key, foreign reference)
   * ``value``: short name for the entry (plain text)

#. Other tables, triggers, views, indexes etc. can also be added and populated when categories are initialised, but they should only contain derived information.

For each category ``{cat}``, the following files are expected in folder ``cats``:

* ``cats/{cat}/schema.json``: `json schema <https://json-schema.org/>`_ describing the entries of category {cat}
* ``cats/{cat}/init.py``: python file initialising category {cat} on server (run once for each version of the xpose instance)
* ``cats/{cat}/{*}`` (optional): utility files for category {cat}, esp. `genshi templates <https://genshi.edgewall.org/>`_

The following sqlite functions are made available in contexts where they are needed:

* :func:`create_attach`(oid,attach): called when an entry is created to set its ``attach`` field in the index, given its ``oid`` and ``attach`` fields (the latter is overridden)
* :func:`delete_attach`(oid): called when an entry with a given ``oid`` field is deleted
* :func:`authorise`(level): controls access to an entry given its level (field ``access`` in the index)
* :func:`apply_template`(tmpl,err_tmpl,rendering,args): applies a genshi template *tmpl* rendered as *rendering* with arguments *args*; in case of error, applies *err_tmpl*
"""

import sqlite3,json
from functools import cached_property
from pathlib import Path
from typing import Optional, Union, Callable, Dict, Any
from .utils import CGIMixin, rebase, http_ts
from .utils import get_config,set_config # not used, but made available
if not hasattr(Path,'hardlink_to'): Path.hardlink_to = lambda self,target: Path(target).link_to(self) # fixes a compatibility issue, useless in python 3.10+
#sqlite3.register_converter('json',json.loads)

#======================================================================================================================
class XposeBase:
  r"""
An instances of this base class is a resource for processing Xpose operations. Actual behaviour is defined in subclasses.
  """
#======================================================================================================================

  root: Path
  r"""Path to the root folder"""
  index_db: Path
  r"""Path to the index database"""

  def setup(self,path:Union[str,Path]='.'):
    self.root = Path(path).resolve()
    self.index_db = self.root/'index.db'
    return self

#----------------------------------------------------------------------------------------------------------------------
  def connect(self,**ka):
    r"""
Returns a :class:`sqlite3.Connection` opened on the index database. The keyword arguments *ka* are passed as such to the connection constructor.
    """
#----------------------------------------------------------------------------------------------------------------------
    return sqlite3.connect(self.index_db,**ka)

#======================================================================================================================
class WithCatsMixin:
#======================================================================================================================
  root: Path
  @cached_property
  def cats(self)->'Cats': return Cats(self.root/'cats')

#======================================================================================================================
class XposeClient (XposeBase,WithCatsMixin,CGIMixin):
  r"""
An instance of this class is a CGI resource managing (restricted) client access to the Xpose index database through prepared SQL queries.
  """
#======================================================================================================================

  authorise: Callable[[str],bool]
  r"""Function controlling access to the entries of this instance"""
  prepared: dict[str,tuple[str,...]]
  r"""Mapping query names to actual SQL queries (with variables)"""

  def __init__(self,authorise=(lambda level: False),prepared:Dict[str,tuple[str,...]]={}):
    self.authorise = authorise
    self.prepared = prepared

  def connect(self,**ka):
    conn = super().connect(**ka)
    conn.create_function('authorise',1,self.authorise)
    conn.create_function('xpose_template',4,(lambda tmpl,err_tmpl,rendering,args,t=self.cats.apply_template:t(tmpl,err_tmpl,rendering,xpose=self,**json.loads(args))))
    return conn

  def do_get(self):
    form = self.parse_qsl()
    sql,*args = self.prepared[form['sql']]
    args = tuple(map(form.get,args))
    with self.connect() as conn:
      conn.row_factory = sqlite3.Row
      resp = [dict(r) for r in conn.execute(sql,args).fetchall()]
      return json.dumps(resp), {'Content-Type':'text/json','Last-Modified':http_ts(self.index_db.stat().st_mtime)}

  @cached_property
  def url_base(self): return self.from_server_root(self.root)
  def rebase(self,x:str,path:Union[str,Path]): return rebase(x,str(self.url_base/'attach'/path/'_'))

#======================================================================================================================
class Cats:
  r"""
An instance of this class manages all the xpose instance's categories (field ``cat`` in the index).
  """
#======================================================================================================================

  validators: dict[str,Any]

  def __init__(self,root:Path):
    self.root = root.resolve()
    self.validators = {}

#----------------------------------------------------------------------------------------------------------------------
  def initial(self,**ka):
    r"""
Initialises all the categories found (file ``init.py`` in any recursive sub-folder of ``cats``).
    """
#----------------------------------------------------------------------------------------------------------------------
    for pcat in self.root.glob('**/init.py'):
      exec(pcat.read_text(),{'cat':str(pcat.relative_to(self.root).parent),**ka})

#----------------------------------------------------------------------------------------------------------------------
  def validate(self,cat:str,value:object):
    r"""
Checks that *value*, viewed as a json object, conforms to the json schema associated with *cat*.

:param cat: the category against which to validate
:param value: the value to validate
    """
#----------------------------------------------------------------------------------------------------------------------
    validator = self.validators.get(cat)
    if validator is None:
      from jsonschema import Draft202012Validator,RefResolver
      base = self.root/cat/'schema.json'
      with base.open() as u: schema = json.load(u)
      Draft202012Validator.check_schema(schema)
      self.validators[cat] = validator = Draft202012Validator(schema=schema).evolve(resolver=RefResolver(f'file://{base}',{}))
    validator.validate(value)

  @cached_property
  def template_loader(self):
    from genshi.template import TemplateLoader
    return TemplateLoader(str(self.root),auto_reload=True)
  def load_template(self,tmpl):
    return self.template_loader.load(tmpl)
#----------------------------------------------------------------------------------------------------------------------
  def apply_template(self,tmpl:str,err_tmpl:str,rendering:Union[str,None],**args):
    r"""
Applies a template specified by *tmpl* with a set of variables specified by *args*. All templates are found in folder ``templates`` with relative path specifying the template role and category, and suffix ``.xhtml``.

:param tmpl: genshi template path (relative to the root)
:param err_tmpl: genshi template path, executed, with no variable, in case of error
    """
#----------------------------------------------------------------------------------------------------------------------
    try: return self.load_template(tmpl).generate(**args).render(rendering)
    except: return self.load_template(err_tmpl).generate().render(rendering)
