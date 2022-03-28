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
"""

import sys,os,sqlite3,shutil,json,re,traceback,dill as pickle
from functools import cached_property, cache, singledispatch
from datetime import datetime
from pathlib import Path
from http import HTTPStatus
from urllib.parse import parse_qsl,urljoin
from typing import Union, Callable, Dict, Any
from enum import Enum
from attach import Attach
from access import Accessor
from utils import rebase,CGIMixin,http_ts
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
  attach: 'Attach'
  r"""Object managing the attachments associated to this instance"""
  cats: 'Cats'
  r"""Object managing the categories associated to this instance"""
  attach_namer:Any
  r"""Object implementing the encoding-decoding of entry ids"""
  accessor:Accessor
  r"""Object controlling access to this instance"""

  def __init__(self,root:Union[str,Path]='.',attach_namer=None,accessor=None):
    self.root = root = Path(root).resolve()
    self.accessor = accessor
    self.attach = Attach((root/'attach').resolve(),attach_namer)
    self.cats = Cats((root/'cats').resolve())
    self.index_db = (root/'index.db').resolve()

#----------------------------------------------------------------------------------------------------------------------
  def connect(self,**ka):
    r"""
Returns a :class:`sqlite3.Connection` opened on the index database. The keyword arguments *ka* are passed as such to the connection constructor. Two user defined sqlite functions are made available:

* :func:`create_attach` (arity 2): called when an entry is created to set its ``attach`` field in the index, given its ``oid`` and ``attach`` fields (the latter is overridden)
* :func:`delete_attach` (arity 1): called when an entry is deleted
* :func:`authorise` (arity 1): controls access to an entry given its level (field ``access`` in the index)
* :func:`apply_template` (arity 4): invokes method :meth:`apply_template` on the object held by the :attr:`cats` attribute; variable ``xpose`` denotes this instance
    """
#----------------------------------------------------------------------------------------------------------------------
    conn = sqlite3.connect(self.index_db,**ka)
    conn.create_function('create_attach',2,(lambda oid,attach,convert=self.attach.namer.int2str:convert(oid)))
    conn.create_function('delete_attach',1,(lambda attach,rmdir=self.attach.rmdir:rmdir(attach,True)))
    conn.create_function('authorise',1,self.accessor.authorise)
    conn.create_function('xpose_template',4,(lambda tmpl,err_tmpl,rendering,args,t=self.cats.apply_template:t(tmpl,err_tmpl,rendering,xpose=self,**json.loads(args))))
    return conn

  @cached_property
  def url_base(self): return Path('/'+str(self.root.relative_to(os.environ['DOCUMENT_ROOT'])))
  def rebase(self,x:str,path:Union[str,Path]): return rebase(x,str(self.url_base/'attach'/path/'_'))

#======================================================================================================================
class XposeClient (XposeBase,CGIMixin):
  r"""
An instance of this class is a CGI resource managing (restricted) client access to the Xpose index database through prepared SQL queries.
  """
#======================================================================================================================
  def __init__(self,prepared:Dict[str,tuple[str,...]]=None,**ka):
    super().__init__(**ka)
    self.prepared = prepared or {}

  def do_get(self):
    form = dict(parse_qsl(os.environ['QUERY_STRING']))
    sql,*args = self.prepared[form['sql']]
    args = tuple(map(form.get,args))
    with self.connect() as conn:
      conn.row_factory = sqlite3.Row
      resp = [dict(r) for r in conn.execute(sql,args).fetchall()]
      return json.dumps(resp), {'Content-Type':'text/json','Last-Modified':http_ts(self.index_db.stat().st_mtime)}

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
