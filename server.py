import sys,sqlite3,shutil,json,traceback,dill as pickle
from functools import cached_property
from datetime import datetime
from pathlib import Path
from typing import Union, Callable, Dict, Any
from . import XposeBase
from utils import CGIMixin,http_raise,http_ts,parse_input

XposeSchema = '''
CREATE TABLE Entry (
  oid INTEGER PRIMARY KEY AUTOINCREMENT,
  version INTEGER NOT NULL,
  cat TEXT NOT NULL,
  value JSON NOT NULL,
  attach TEXT NULLABLE,
  created DATETIME NOT NULL,
  modified DATETIME NOT NULL,
  access TEXT NULLABLE,
  memo JSON NULLABLE
);

CREATE TRIGGER EntryAttach AFTER INSERT ON Entry
  BEGIN UPDATE Entry SET attach=create_attach(oid,attach) WHERE oid=NEW.oid; END;

CREATE TRIGGER EntryDelete AFTER DELETE ON Entry
  BEGIN SELECT delete_attach(OLD.attach); END;

CREATE INDEX EntryIndexCat ON Entry ( cat );
CREATE INDEX EntryIndexModified ON Entry ( modified );
CREATE UNIQUE INDEX EntryIndexCreated ON Entry ( created );

CREATE TABLE Short (
  entry INTEGER PRIMARY KEY REFERENCES Entry ON DELETE CASCADE,
  value TEXT NOT NULL
) WITHOUT ROWID;
'''

#======================================================================================================================
class XposeServer (XposeBase,CGIMixin):
  r"""
An instance of this class provides various management operations on an Xpose instance.
  """
#======================================================================================================================

#----------------------------------------------------------------------------------------------------------------------
  def load(self,content:Union[str,Path,list],with_oid:bool=False):
    r"""
Loads some entries in the index database. Entries are validated, and behaviour is transactional. If *with_oid* is :const:`True` (resp. :const:`False`), the entries must have (resp. not have) an ``oid`` field. If present, the ``oid`` field must of course be different from any existing one (an error is raised otherwise). Furthermore, the ``attach`` field must be either :const:`None` or a dictionary where each key is a relative path within the entry attachment folder and the value is an absolute path to be hard-linked to that local path. Note that folders (which cannot be hard-linked) never need to be explicitly created as attachments, as they are created as need be to store file attachments.

:param content: the list of entries to load into the index database, or a path to a json file containing that list under key ``listing`` (consistent with method :meth:`dump`)
:param with_oid: whether the entries contain their ``oid`` key
    """
#----------------------------------------------------------------------------------------------------------------------
    def get_fields(conn):
      cur = conn.execute('PRAGMA table_info(Entry)')
      n, = (n for n,d in enumerate(cur.description) if d[0]=='name')
      fields = [x[n] for x in cur]
      cur.close()
      return fields
    def entry(row,i):
      assert set(row) == field_set, set(row)^field_set
      value = row['value']
      self.cats.validate(row['cat'],value)
      row['value'] = json.dumps(value)
      memo = row['memo']
      row['memo'] = None if memo is None else json.dumps(memo)
      a = f'{i:04x}'; a = f'{a[:2]}/{a[2:]}' # arbitrary 1-1 encoding of i
      Info[a] = row['attach']; row['attach'] = a
      return tuple(row[f] for f in fields)
    def create_attach(oid,a,enc=self.attach.namer.int2str):
      a = Info[a]
      p = enc(oid)
      root = self.attach.root/p
      if a is not None:
        try:
          for name,src in a.items():
            trg = root/name
            trg.parent.mkdir(parents=True,exist_ok=True)
            trg.hardlink_to(src)
        except:
          traceback.print_exc(file=sys.stderr); raise
      return p
    if isinstance(content,list): listing = content
    else:
      with open(content) as u: listing = json.load(u)['listing']
    with self.connect() as conn:
      conn.create_function('create_attach',2,create_attach) # overrides the default
      fields = get_fields(conn)
      if not with_oid: fields.remove('oid')
      field_set = set(fields)
      sql = f'INSERT INTO Entry ({",".join(fields)}) VALUES ({",".join(len(fields)*["?"])})'
      Info:Dict[str,dict] = {}
      listing = [entry(row,i) for i,row in enumerate(listing)]
      conn.executemany(sql,listing)

#----------------------------------------------------------------------------------------------------------------------
  def dump(self,path:Union[str,Path]=None,clause:str=None,with_oid:bool=False):
    r"""
Extracts a list of entries from the index database. If *with_oid* is :const:`True` (resp. :const:`False`), the entries will have (resp. not have) an ``oid`` field. Furthermore, the ``attach`` field has the same form as in :meth:`load`.

:param path: if not :const:`None`, the extracted list is dumped into a json file at *path* (under key ``listing``) and :const:`None` is returned
:param clause: specifies extra SQL clauses (WHERE, ORDER BY, LIMIT...) to extract the entries (if absent, all the entries are extracted)
:param with_oid: if :const:`True`, the entries will include their ``oid`` key
    """
#----------------------------------------------------------------------------------------------------------------------
    def trans(row):
      row = dict(row)
      if not with_oid: del row['oid']
      p = self.attach.root/row['attach']
      row['attach'] = dict((str(f.relative_to(p)),str(f)) for f in p.glob('**/*') if not f.is_dir()) or None
      row['value'] = json.loads(row['value'])
      row['memo'] = json.loads(row['memo'] or 'null')
      return row
    clause_ = '' if clause is None else f' {clause}'
    with self.connect() as conn:
      conn.row_factory = sqlite3.Row
      listing = list(map(trans,conn.execute(f'SELECT * FROM Entry{clause_}').fetchall()))
      ts = datetime.now().isoformat(timespec='seconds')
    if path is None: return listing
    with open(path,'w') as v:
      json.dump({'meta':{'origin':'XposeDump','timestamp':ts,'root':str(self.root),'clause':clause},'listing':listing},v,indent=1)

#----------------------------------------------------------------------------------------------------------------------
  def precompute_trigger(self,table:str,cat:str,defn:str,when:str=None):
    r"""
Declares a trigger on ``INSERT`` or ``UPDATE`` operations on the ``Entry`` table, when the ``cat`` field is *cat*. The triggered action must be an insertion into *table*.

:param table: the target table populated by the trigger
:param cat: the category (field ``cat``) for which the trigger executes
:param when: (optional) additional condition for the trigger to execute
:param defn: what to insert in the target table, as an SQL ``SELECT`` statement or ``VALUES`` clause
    """
#----------------------------------------------------------------------------------------------------------------------
    def create_trigger(op,delete):
      return f'''
CREATE TRIGGER {table}Trigger{op.split(' ',1)[0].title()}{''.join(z.title() for z in cat.split('/'))}{when_}
AFTER {op} ON Entry WHEN NEW.cat='{cat}'{when}
BEGIN
  {delete}INSERT INTO {table}
{defn};
END'''
    defn = '\n'.join(f'    {x}' for x in defn.split('\n') if x.strip())
    when,when_ = ('','') if when is None else (f' AND {when}',f'{sum(ord(x) for x in when):05x}')
    script = ';\n'.join(create_trigger(*x) for x in (('INSERT',''),('UPDATE OF value',f'DELETE FROM {table} WHERE entry=OLD.oid;\n  ')))
    with self.connect() as conn: conn.executescript(script)

#----------------------------------------------------------------------------------------------------------------------
  @classmethod
  def initial(cls,root:Union[str,Path]='.',config:dict[str,Any]=None):
    r"""
Creates an initial xpose instance in a root folder.

:param root: a path to the instance
    """
#----------------------------------------------------------------------------------------------------------------------
    cats = Path(cats).resolve()
    assert cats.is_dir()
    for _f in cats.iterdir(): pass # check readable
    upgrader = Path(upgrader).resolve()
    assert upgrader.is_file()
    exec(upgrader.read_text(),{}) # check readable and pythonic
    root = Path(root).resolve()
    root.mkdir()
    with (root/'.config').open('wb') as v: pickle.dump(config,v)
    (root/'cats').symlink_to(cats)
    (root/'upgrader.py').symlink_to(upgrader)
    (root/'attach').mkdir(); (root/'attach'/'.uploaded').mkdir()
    (root/'.htacess').write_text('<FilesMatch ".*\\.db$">\nRequire all denied\n</FilesMatch>')
    self = cls(root)
    with self.connect() as conn: conn.executescript(XposeSchema)
    return self

  @staticmethod
  def status(xpose:'XposeServer'):
    with xpose.connect(isolation_level='IMMEDIATE') as conn:
      version, = conn.execute('PRAGMA user_version').fetchone()
      stats = {
        'cat': dict(conn.execute('SELECT cat,count(*) as cnt FROM Entry GROUP BY cat ORDER BY cnt DESC')),
        'access': dict(conn.execute('SELECT coalesce(access,\'\'),count(*) as cnt FROM Entry GROUP BY access ORDER BY cnt DESC')),
      }
      ts = xpose.index_db.stat().st_mtime
    shadow = None
    if xpose.upgrader.get(version) is not None:
      try: shadow = xpose.status(XposeServer(root=xpose.root/'shadow'))
      except: shadow = {'version':-1}
    return dict(ts=ts,version=version,shadow=shadow,stats=stats)

  @cached_property
  def upgrader(self)->dict[int,Callable[[XposeBase],tuple[Union[str,Path],str,dict[str,Any],list]]]:
    ns = {}
    exec((self.root/'upgrader.py').read_text(),ns)
    return dict((int(k[9:]),upg) for k,upg in ns.items() if k.startswith('upgrader_'))

#----------------------------------------------------------------------------------------------------------------------
  def do_get(self):
    r"""
Returns the available upgrade if any.
    """
#----------------------------------------------------------------------------------------------------------------------
    s = self.status(self)
    return json.dumps(s),{'Content-Type':'text/json','Last-Modified':http_ts(s['ts'])}

#----------------------------------------------------------------------------------------------------------------------
  def do_post(self):
    r"""
No input expected.
    """
#----------------------------------------------------------------------------------------------------------------------
    status = self.status(self)
    version = status['version']
    upgrader = self.upgrader.get(version)
    assert upgrader is not None
    listing = upgrader(self)
    listing.sort(key=(lambda entry: entry['created']))
    p = self.root/'shadow'
    if p.exists(): shutil.rmtree(p)
    shadow = XposeServer.initial(p,upgrader=self.root/'upgrader.py')
    version += 1
    with shadow.connect() as conn:
      if schema: conn.executescript(schema)
      conn.execute(f'PRAGMA user_version = {version}')
    shadow.load(listing)
    status.update(shadow=self.status(shadow))
    return json.dumps(status),{'Content-Type':'text/json'}
