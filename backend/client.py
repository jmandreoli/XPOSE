# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: client CGI resource
#

r"""
:mod:`XPOSE.client` --- client CGI resource
===========================================
"""

import sqlite3,json
from functools import cached_property
from pathlib import Path
from typing import Optional, Union, Callable, Dict, Any
from .utils import CGIMixin, rebase, http_ts
from . import XposeBase, WithCatsMixin

#======================================================================================================================
class XposeClient (XposeBase,WithCatsMixin,CGIMixin):
  r"""
An instance of this class is a CGI resource managing (restricted, read-only) client access to the Xpose index database through prepared SQL queries.

:param authorise: callable taking as input an access level and returning whether access is authorised
:param prepared: dictionary mapping each sql query name to an actual query with (possibly) named parameters
  """
#======================================================================================================================

  def __init__(self,authorise:Callable[[str],bool]=(lambda level: False),prepared:dict[str,str]={}):
    self.authorise = authorise
    self.prepared = prepared

  def connect(self,**ka):
    r"""
Same as base, but adds sqlite functions ``authorise`` and ``xpose_template``.
    """
    conn = super().connect(**ka)
    conn.create_function('authorise',1,self.authorise,deterministic=True)
    conn.create_function('xpose_template',4,(lambda tmpl,err_tmpl,rendering,args,t=self.cats.apply_template:t(tmpl,err_tmpl,rendering,xpose=self,**json.loads(args))),deterministic=True)
    return conn

#----------------------------------------------------------------------------------------------------------------------
  def do_get(self):
    r"""
Input: url-encoded form with one field ``sql`` whose value is the name of a prepared sql query; the other fields provide the named parameters in that query.

Output (text/json): list of entries resulting from the execution of the query; each row is a dictionary where the fields are column names from the query.
    """
#----------------------------------------------------------------------------------------------------------------------
    form = self.parse_qsl()
    sql = self.prepared[form['sql']]
    with self.connect() as conn:
      conn.row_factory = sqlite3.Row
      resp = [dict(r) for r in conn.execute(sql,form)]
      return json.dumps(resp), {'Content-Type':'text/json','Last-Modified':http_ts(self.index_db.stat().st_mtime)}

  @cached_property
  def url_base(self): return self.from_server_root(self.root)
  def rebase(self,x:str,path:Union[str,Path]): return rebase(x,str(self.url_base/'attach'/path/'_'))
