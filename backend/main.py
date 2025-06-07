# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: dashboard CGI resources
#

import sqlite3,json
from datetime import datetime, UTC
from pathlib import Path
from http import HTTPStatus
from typing import Callable, Dict, Any
from . import XposeBase
from .attach import WithAttachMixin
from .utils import CGIMixin,http_raise,http_ts,default_attach_namer

#======================================================================================================================
class XposeMain (XposeBase,WithAttachMixin,CGIMixin):
  r"""
An instance of this class is a CGI resource managing the index database of an Xpose instance.

:param authoriser: callable taking as input an access level and a path, and restricting access to that path to that level
:param attach_namer: callable taking as input an entry oid and returning a string suitable as a path name for attachments of that entry
  """
#======================================================================================================================

  def __init__(self,authoriser:Callable[[str,Path],None]=(lambda level,path: None),attach_namer:Callable[[int],str]=default_attach_namer):
    self.authoriser = authoriser
    self.attach_namer = attach_namer

  def connect(self,**ka):
    r"""
Same as base, but adds sqlite functions ``create_attach``, ``delete_attach`` and ``authoriser``
    """
    conn = super().connect(**ka)
    conn.create_function('create_attach',1,self.attach_namer,deterministic=True)
    conn.create_function('delete_attach',1,self.attach.rmdir,deterministic=True)
    conn.create_function('authoriser',2,(lambda access,attach,auth=self.authoriser,root=self.attach.root: auth(access,root/attach)),deterministic=True)
    return conn

#----------------------------------------------------------------------------------------------------------------------
  def do_get(self):
    r"""
Input: url-encoded form with one field ``sql`` whose value is a sql query (SELECT only); the other fields provide the named parameters in that query.

Output (text/json): list of entries resulting from the execution of the query; each row is a dictionary where the fields are column names from the query.
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
Input: JSON encoded dict, either inserted as a new entry in Xpose or used to update an existing one (depending on the presence of attribute ``oid``). No validation is performed.

Output (text/json): JSON encoded dict with keys ``oid``, ``version``, ``short``, ``attach`` characterising the new or updated entry.
    """
#----------------------------------------------------------------------------------------------------------------------
    entry = self.parse_input()
    oid,version,access,value = entry.get('oid'),entry.get('version'),entry['access'],json.dumps(entry['value'])
    now = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S.%f')
    if oid is None:
      version=0
      sql = 'INSERT INTO Entry (version,cat,value,created,modified,access) VALUES (?,?,?,?,?,?) RETURNING oid',(version+1,entry['cat'],value,now,now,access)
    else:
      version = int(version)
      sql = 'UPDATE Entry SET version=iif(version=?,?,NULL),value=?,modified=?,access=? WHERE oid=? RETURNING oid',(version,version+1,value,now,access,int(oid))
    with self.connect() as conn:
      try: oid, = conn.execute(*sql).fetchone()
      except sqlite3.IntegrityError: http_raise(HTTPStatus.CONFLICT)
      short,attach = conn.execute('SELECT short,attach FROM EntryShort WHERE oid=?',(oid,)).fetchone()
    return json.dumps({'oid':oid,'version':version+1,'short':short,'attach':attach}), {'Content-Type':'text/json'}

#----------------------------------------------------------------------------------------------------------------------
  def do_delete(self):
    r"""
Input: JSON encoded dict with a single key ``oid``, which must denote the primary key of an Entry to be deleted.

Output (text/json): JSON encoded dict with key ``oid`` of the deleted entry.
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
Input: url-encoded form with a single field ``path`` (which must point to a directory).

Output (text/json): JSON encoded dict with keys ``content``, ``version`` and ``toplevel`` characterising the queried path.
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
Input: JSON encoded dict with keys ``path``, ``version`` and ``ops``, the latter being a list of operations. An operation is specified as a dict with keys ``src``, ``trg`` (relative paths) and ``is_new`` (boolean).

Output (text/json): Same as method :meth:`do_get`, characterising the queried path after the list of operations has been executed. If errors have occurred, they are stored under key ``error``.
    """
#----------------------------------------------------------------------------------------------------------------------
    content = self.parse_input()
    path,version,ops = content['path'],content['version'],content['ops']
    with self.connect(isolation_level='IMMEDIATE'): # ensures isolation of attachment operations, no transaction is performed
      path,level = self.attach.getpath(path)
      if self.version(path) != version: http_raise(HTTPStatus.CONFLICT)
      errors = [err for op in ops if (err:=self.attach.perform(path,op['src'].strip(),op['trg'].strip(),bool(op['is_new']))) is not None]
      content = self.attach.ls(path)
      if level==0: content = [x for x in content if not x[0].endswith('.htaccess')]
      version = self.version(path)
    return json.dumps({'content':content,'version':version,'toplevel':level==0,'errors':errors}), {'Content-Type':'text/json'}

#----------------------------------------------------------------------------------------------------------------------
  def do_post(self):
    r"""
Input: octet stream of uploaded file chunks.

Output (text/json): JSON encoded dict with keys ``name``, ``mtime`` and ``size``.
    """
#----------------------------------------------------------------------------------------------------------------------
    it = self.parse_input('application/octet-stream',chunk=self.chunk)
    res = self.attach.upload(it)
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
