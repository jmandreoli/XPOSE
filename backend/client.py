# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: client CGI resource
#

import sqlite3,json
from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import Optional, Union, Callable, Dict, Any
from . import XposeBase, WithCatsMixin
from .utils import CGIMixin, rebase, http_ts

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
Same as base, but adds sqlite functions ``authorise``, ``uid2key``, ``key2uid`` and ``xpose_template``.
    """
    conn = super().connect(**ka)
    conn.create_function('authorise',1,self.authorise,deterministic=True)
    conn.create_function('uid2key',1,(lambda uid:f'{datetime.fromtimestamp(int(uid[:-5],16)).isoformat()}.{int(uid[-5:],16):06d}'),deterministic=True)
    conn.create_function('key2uid',1,(lambda key:(lambda key_:f'{int(datetime.fromisoformat(key_[0]).timestamp()):x}{int(key_[1]):05x}')(key.split('.',1))),deterministic=True)
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
  def rebase(self,x:str,path:str|Path): return rebase(x,str(self.url_base/'attach'/path/'_'))
