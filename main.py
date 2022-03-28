import os,sqlite3,json
from datetime import datetime
from pathlib import Path
from http import HTTPStatus
from urllib.parse import parse_qsl
from typing import Union, Callable, Dict, Any
from . import XposeBase
from utils import CGIMixin,http_raise,http_ts,parse_input

#======================================================================================================================
class XposeMain (XposeBase,CGIMixin):
  r"""
An instance of this class is a CGI resource managing the Xpose index database.
  """
#======================================================================================================================

  sql_oid = '''SELECT oid,version,cat,Short.value as short,Entry.value as value,attach,access
    FROM Entry LEFT JOIN Short ON Short.entry=oid
    WHERE oid=?'''

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
        return [dict(r) for r in conn.execute(*a).fetchall()], self.index_db.stat().st_mtime
    form = dict(parse_qsl(os.environ['QUERY_STRING']))
    resp = ''
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
  def do_post(self):
    r"""
Input is expected as a JSON encoded object with a single field ``sql``, which must denote an arbitrary SQLite script.
    """
#----------------------------------------------------------------------------------------------------------------------
    form = parse_input()
    sql = form['sql'].strip()
    with self.connect() as conn:
      c = conn.executescript(sql)
      return dict(total_changes=conn.total_change,lastrowid=c.lastrowid), {'Content-Type':'text/json'}

#----------------------------------------------------------------------------------------------------------------------
  def do_put(self):
    r"""
Input is expected as any JSON encoded entry. Validation is not performed.
    """
#----------------------------------------------------------------------------------------------------------------------
    entry = parse_input()
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
      self.accessor.authorise_folder(access,self.attach.root/attach)
    return json.dumps({'oid':oid,'version':version+1,'short':short,'attach':attach}), {'Content-Type':'text/json'}

#----------------------------------------------------------------------------------------------------------------------
  def do_delete(self):
    r"""
Input is expected as a JSON encoded object with a single field ``oid``, which must denote the primary key of an Entry.
    """
#----------------------------------------------------------------------------------------------------------------------
    oid = parse_input()['oid']
    with self.connect() as conn:
      conn.execute('PRAGMA foreign_keys = ON')
      conn.execute('DELETE FROM Entry WHERE oid=?',(oid,))
    return json.dumps({'oid':oid}), {'Content-Type':'text/json'}

#----------------------------------------------------------------------------------------------------------------------
  def do_head(self):
#----------------------------------------------------------------------------------------------------------------------
    http_raise(HTTPStatus.NOT_IMPLEMENTED)
