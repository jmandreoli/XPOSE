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
from .utils import CGIMixin,http_raise,http_ts

#======================================================================================================================
class XposeMain (XposeBase,WithAttachMixin,CGIMixin):
  r"""
An instance of this class is a CGI resource managing the Xpose index database.
  """
#======================================================================================================================

  attach_namer: Callable[[int],str]
  r"""Function mapping an oid into a (relative) folder pathname"""
  authoriser: Callable[[str,Path],None]
  r"""Function setting the access authorisation level for a folder"""
  sql_oid = '''SELECT oid,version,cat,Short.value as short,Entry.value as value,attach,access
    FROM Entry LEFT JOIN Short ON Short.entry=oid
    WHERE oid=?'''
  r"""The SQL query to retrieve an entry given its oid"""

  def __init__(self,authoriser=None,attach_namer=None,**ka):
    self.authoriser = authoriser
    self.attach_namer = attach_namer

  def connect(self,**ka):
    conn = super().connect(**ka)
    conn.create_function('create_attach',2,(lambda oid,attach,namer=self.attach_namer: namer(oid)))
    conn.create_function('delete_attach',1,(lambda attach,rmdir=self.attach.rmdir:rmdir(attach,True)))
    conn.create_function('authoriser',2,(lambda access,attach,auth=self.authoriser,root=self.attach.root: auth(access,root/attach)))
    return conn

#----------------------------------------------------------------------------------------------------------------------
  def do_get(self):
    r"""
Input is expected as an (encoded) form with a single field. The field must be either of

* ``sql``: value must denote an SQLite query of type ``SELECT`` only. Output is the JSON formatted list of rows returned by the query. Each item in the list is a dictionary.
* ``oid``: value must denote the key of a unique entry. Output is the corresponding JSON formatted entry, as a dictionary.
    """
#----------------------------------------------------------------------------------------------------------------------
    def select_all(*a):
      with self.connect() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(*a)], self.index_db.stat().st_mtime
    form = self.parse_qsl()
    resp,ts = '',None
    if (sql:=form.get('sql')) is not None:
      sql = sql.strip()
      assert sql.lower().startswith('select ')
      resp,ts = select_all(sql)
      resp = json.dumps(resp)
    elif (oid:=form.get('oid')) is not None:
      oid = int(oid)
      (r,),ts = select_all(self.sql_oid,(oid,))
      r['short'] = r['short'].replace('"',r'\"')
      r['access'] = (lambda x: 'null' if x is None else f'"{x}"')(r['access'])
      resp = '{{"oid":{oid},"version":{version},"cat":"{cat}","short":"{short}","value":{value},"attach":"{attach}","access":{access}}}'.format(**r)
    else: http_raise(HTTPStatus.NOT_FOUND)
    return resp, {'Content-Type':'text/json','Last-Modified':http_ts(ts)}

#----------------------------------------------------------------------------------------------------------------------
  def do_put(self):
    r"""
Input is expected as any JSON encoded entry. Validation is not performed.
    """
#----------------------------------------------------------------------------------------------------------------------
    entry = self.parse_input()
    oid,version,access,value = entry.get('oid'),entry.get('version'),entry['access'],json.dumps(entry['value'])
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if oid is None:
      version=0
      sql = 'INSERT INTO Entry (version,cat,value,created,modified,access) VALUES (?,?,?,?,?,?)',(version+1,entry['cat'],value,now,now,access)
    else:
      version = int(version)
      sql = 'UPDATE Entry SET version=iif(version=?,?,NULL),value=?,modified=?,access=? WHERE oid=?',(version,version+1,value,now,access,int(oid))
    with self.connect() as conn:
      try: res = conn.execute(*sql)
      except sqlite3.IntegrityError: http_raise(HTTPStatus.CONFLICT)
      if oid is None: oid = res.lastrowid
      attach,short = conn.execute('SELECT attach,Short.value FROM Entry,Short WHERE Short.entry=? AND oid=?',(oid,oid)).fetchone()
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
  """
#======================================================================================================================

  chunk: int
  r"""Controls the chunk size for file upload"""

  def __init__(self,chunk:int=0x100000):
    self.chunk = chunk

#----------------------------------------------------------------------------------------------------------------------
  def do_get(self):
    r"""
Input is expected as an (encoded) form with a single field ``path``.
    """
#----------------------------------------------------------------------------------------------------------------------
    form = self.parse_qsl()
    path,level = self.attach.getpath(form['path'])
    content = self.attach.ls(path)
    if level==0: content = [x for x in content if not x[0].endswith('.htaccess')] # XXXX specific to one authoriser, may use .xpose-hide-filename
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
