# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: index database operations
#

import sqlite3,json
from datetime import datetime
from pathlib import Path
from http import HTTPStatus
from typing import Union, Callable, Dict, Any
from . import XposeBase
from .attach import WithAttachMixin
from .utils import CGIMixin,http_raise,http_ts,default_attach_namer

#======================================================================================================================
class XposeMain (XposeBase,WithAttachMixin,CGIMixin):
  r"""
An instance of this class is a CGI resource managing the index database of an Xpose instance.

:param authoriser: callable taking as input an access level and a path, and restricting access to that path to that level
:param attach_namer: callable taking as input an entry oid and returning a string suitable as a path name for attachment
  """
#======================================================================================================================

  def __init__(self,authoriser:Callable[[str,Path],None]=(lambda level,path: None),attach_namer:Callable[[int],str]=default_attach_namer):
    self.authoriser = authoriser
    self.attach_namer = attach_namer

  def connect(self,**ka):
    conn = super().connect(**ka)
    conn.create_function('create_attach',1,self.attach_namer,deterministic=True)
    conn.create_function('delete_attach',1,self.attach.rmdir,deterministic=True)
    conn.create_function('authoriser',2,(lambda access,attach,auth=self.authoriser,root=self.attach.root: auth(access,root/attach)),deterministic=True)
    return conn

#----------------------------------------------------------------------------------------------------------------------
  def do_get(self):
    r"""
Input is expected as an (encoded) form with one field ``sql`` whose value is a sql query (SELECT only), plus fields to fill the named parameters in that query.
    """
#----------------------------------------------------------------------------------------------------------------------
    form = self.parse_qsl()
    sql = form['sql'].strip()
    assert sql.lower().startswith('select ')
    with self.connect(detect_types=sqlite3.PARSE_COLNAMES) as conn:
      conn.row_factory = sqlite3.Row
      resp = [dict(r) for r in conn.execute(sql,form)]
      return json.dumps(resp), {'Content-Type':'text/json','Last-Modified':http_ts(self.index_db.stat().st_mtime)}

#----------------------------------------------------------------------------------------------------------------------
  def do_put(self):
    r"""
Input is expected as any JSON encoded entry. Validation is not performed.
    """
#----------------------------------------------------------------------------------------------------------------------
    entry = self.parse_input()
    oid,version,access,value = entry.get('oid'),entry.get('version'),entry['access'],json.dumps(entry['value'])
    now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')
    if oid is None:
      version=0
      sql = 'INSERT INTO Entry (version,cat,value,created,modified,access) VALUES (?,?,?,?,?,?) RETURNING oid',(version+1,entry['cat'],value,now,now,access)
    else:
      version = int(version)
      sql = 'UPDATE Entry SET version=iif(version=?,?,NULL),value=?,modified=?,access=? WHERE oid=? RETURNING oid',(version,version+1,value,now,access,int(oid))
    with self.connect() as conn:
      try: oid, = conn.execute(*sql).fetchone()
      except sqlite3.IntegrityError: http_raise(HTTPStatus.CONFLICT)
      short,attach = conn.execute('SELECT Short.value,Entry.attach FROM Entry,Short WHERE oid=? AND entry=oid',(oid,)).fetchone()
    return json.dumps({'oid':oid,'version':version+1,'short':short,'attach':attach}), {'Content-Type':'text/json'}

#----------------------------------------------------------------------------------------------------------------------
  def do_delete(self):
    r"""
Input is expected as a JSON encoded object with a single field ``oid``, which must denote the primary key of an Entry.
    """
#----------------------------------------------------------------------------------------------------------------------
    oid = self.parse_input()['oid']
    with self.connect() as conn: conn.execute('DELETE FROM Entry WHERE oid=?',(oid,))
    return json.dumps({'oid':oid}), {'Content-Type':'text/json'}

#======================================================================================================================
class XposeAttach (XposeBase,WithAttachMixin,CGIMixin):
  r"""
An instance of this class is a CGI resource managing the Xpose attachment folder.

:param chunk: the max size (in MiB) used for buffering large file upload transfer
  """
#======================================================================================================================

  chunk: int
  r"""Controls the chunk size (in bytes) for file upload"""

  def __init__(self,chunk:int=1):
    self.chunk = chunk*0x100000

#----------------------------------------------------------------------------------------------------------------------
  def do_get(self):
    r"""
Input is expected as an (encoded) form with a single field ``path``.
    """
#----------------------------------------------------------------------------------------------------------------------
    form = self.parse_qsl()
    path,level = self.attach.getpath(form['path'])
    content = self.attach.ls(path)
    if level==0: content = [x for x in content if not x[0].endswith('.htaccess')] # XXXX specific to one authoriser, may use .xpose-hide-filename, also in patch
    return json.dumps({'content':content,'version':self.version(path),'toplevel':level==0}),{'Content-Type':'text/json'}

#----------------------------------------------------------------------------------------------------------------------
  def do_patch(self):
    r"""
Input is expected as a JSON encoded object with fields ``path``, ``version`` and ``ops``, the latter being a list of operations. An operation is specified as an object with fields ``src``, ``trg`` (relative paths) and ``is_new`` (boolean).
    """
#----------------------------------------------------------------------------------------------------------------------
    content = self.parse_input()
    path,version,ops = content['path'],content['version'],content['ops']
    with self.connect(isolation_level='IMMEDIATE'): # ensures isolation of attachment operations, no transaction is performed
      path,level = self.attach.getpath(path)
      if self.version(path) != version: http_raise(HTTPStatus.CONFLICT)
      errors = [err for op in ops if (err:=self.attach.do(path,op['src'].strip(),op['trg'].strip(),bool(op['is_new']))) is not None]
      content = self.attach.ls(path)
      if level==0: content = [x for x in content if not x[0].endswith('.htaccess')]
      version = self.version(path)
    return json.dumps({'content':content,'version':version,'toplevel':level==0,'errors':errors}), {'Content-Type':'text/json'}

#----------------------------------------------------------------------------------------------------------------------
  def do_post(self):
    r"""
Input is expected as an octet stream.
    """
#----------------------------------------------------------------------------------------------------------------------
    form = self.parse_qsl()
    it = self.parse_input('application/octet-stream',chunk=self.chunk)
    res = self.attach.upload(it,form.get('target'))
    content = dict(zip(('name','mtime','size'),res))
    return json.dumps(content), {'Content-Type':'text/json'}

#----------------------------------------------------------------------------------------------------------------------
  @staticmethod
  def version(path:Path):
#----------------------------------------------------------------------------------------------------------------------
    if path.exists():
      s = path.stat()
      return [s.st_ino,s.st_mtime]
    else: return None
