# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: instance management operations
#

import sys,sqlite3,shutil,json,traceback
from datetime import datetime
from pathlib import Path
from typing import Union, Callable, Dict, Any
from . import XposeBase, Cats
from .attach import Attach
from .utils import CGIMixin,http_raise,http_ts,parse_input,set_config,get_config

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

CREATE TRIGGER EntryTriggerInsert AFTER INSERT ON Entry
  BEGIN UPDATE Entry SET attach=create_attach(oid,attach) WHERE oid=NEW.oid; END;
CREATE TRIGGER EntryTriggerUpdateAccess AFTER UPDATE OF access ON Entry
  BEGIN SELECT authoriser(NEW.access,NEW.attach); END;
CREATE TRIGGER EntryTriggerUpdateAttach AFTER UPDATE OF attach ON Entry
  BEGIN SELECT authoriser(NEW.access,NEW.attach); END;
CREATE TRIGGER EntryTriggerDelete AFTER DELETE ON Entry
  BEGIN SELECT delete_attach(OLD.attach); END;

CREATE INDEX EntryIndexCat ON Entry ( cat );
CREATE INDEX EntryIndexModified ON Entry ( modified );
CREATE UNIQUE INDEX EntryIndexCreated ON Entry ( created );

CREATE TABLE Short (
  entry INTEGER PRIMARY KEY REFERENCES Entry,
  value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TRIGGER ShortTriggerBeforeDelete BEFORE DELETE ON Entry
  BEGIN DELETE FROM Short WHERE entry=OLD.oid; END;
CREATE TRIGGER ShortTriggerBeforeUpdate BEFORE UPDATE OF value ON Entry
  BEGIN DELETE FROM Short WHERE entry=OLD.oid; END;
'''

#======================================================================================================================
class XposeServer (XposeBase,CGIMixin):
  r"""
An instance of this class provides various management operations on an Xpose instance.
  """
#======================================================================================================================

  def __init__(self,authoriser=None,attach_namer=None,**ka):
    super().__init__(**ka)
    self.authoriser = authoriser
    self.attach_namer = attach_namer
    self.attach = Attach(self.root/'attach')
    self.cats = Cats(self.root/'cats')

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
    def create_attach(oid,a,namer=self.attach_namer,root=self.attach.root):
      a = Info[a]
      attach = namer(oid)
      if a is not None:
        try:
          for name,src in a.items():
            trg = root/attach/name
            trg.parent.mkdir(parents=True,exist_ok=True)
            trg.hardlink_to(src)
        except:
          traceback.print_exc(file=sys.stderr); raise
      return attach
    if isinstance(content,list): listing = content
    else:
      with open(content) as u: listing = json.load(u)['listing']
    with self.connect() as conn:
      conn.create_function('create_attach',2,create_attach) # overrides the default
      conn.create_function('authoriser',2,(lambda access,attach,auth=self.authoriser,root=self.attach.root: auth(access,root/attach)))
      fields = get_fields(conn)
      if not with_oid: fields.remove('oid')
      field_set = set(fields)
      sql = f'INSERT INTO Entry ({",".join(fields)}) VALUES ({",".join(len(fields)*["?"])})'
      Info:Dict[str,dict] = {}
      listing = [entry(row,i) for i,row in enumerate(listing)]
      conn.executemany(sql,listing)

#----------------------------------------------------------------------------------------------------------------------
  def dump(self,clause:str=None,with_oid:bool=False,path:Union[str,Path]=None):
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
      user_version, = conn.execute('PRAGMA user_version').fetchone()
      ts = datetime.now().isoformat(timespec='seconds')
    if path is None: return listing
    with open(path,'w') as v:
      json.dump({'meta':{'origin':'XposeDump','timestamp':ts,'root':str(self.root),'clause':clause,'user_version':user_version},'listing':listing},v,indent=1)

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
    def create_trigger(op):
      return f'''
CREATE TRIGGER {table}Trigger{op.split(' ',1)[0].title()}{cat_}{when_}
AFTER {op} ON Entry WHEN NEW.cat='{cat}'{when}
BEGIN
  INSERT INTO {table}
{defn};
END'''
    defn = '\n'.join(f'    {x}' for x in defn.split('\n') if x.strip())
    cat_ = ''.join(z.title() for z in cat.split('/'))
    when,when_ = ('','') if when is None else (f' AND {when}',f'{sum(ord(x) for x in when):05x}')
    script = ';\n'.join(create_trigger(op) for op in ('INSERT','UPDATE OF value'))
    with self.connect() as conn: conn.executescript(script)

#----------------------------------------------------------------------------------------------------------------------
  def status(self):
#----------------------------------------------------------------------------------------------------------------------
    with self.connect(isolation_level='IMMEDIATE') as conn:
      version, = conn.execute('PRAGMA user_version').fetchone()
      stats = {
        'cat': dict(conn.execute('SELECT cat,count(*) as cnt FROM Entry GROUP BY cat ORDER BY cnt DESC')),
        'access': dict(conn.execute('SELECT coalesce(access,\'\'),count(*) as cnt FROM Entry GROUP BY access ORDER BY cnt DESC')),
      }
      ts = self.index_db.stat().st_mtime
    return dict(root=str(self.root),ts=ts,version=version,stats=stats)

#----------------------------------------------------------------------------------------------------------------------
  def do_get(self):
    r"""
No input expected.
    """
#----------------------------------------------------------------------------------------------------------------------
    s = self.status()
    return json.dumps(s),{'Content-Type':'text/json','Last-Modified':http_ts(s['ts'])}

#----------------------------------------------------------------------------------------------------------------------
  def do_post(self):
    r"""
No input expected.
    """
#----------------------------------------------------------------------------------------------------------------------
    preserve = ()
    if self.root.name == 'shadow': # self is the shadow instance; mirror is the real instance
      mirror = self.root.parent
      upgrader = mirror/'upgrader.py'
      preserve = (self.root,upgrader) # in mirror (real)
    else: # self is the real instance; mirror is the shadow instance
      upgrader = self.root/'upgrader.py'
      mirror = self.root/'shadow'
      cats = mirror/'cats'
      if not cats.exists(): cats.touch() # just to make sure it is there; will be replaced by appropriate symlink
      preserve = (cats,) # in mirror (shadow)
    upgrade = {}; exec(upgrader.read_text(),upgrade)
    # collect self entries
    with self.connect() as conn: user_version, = conn.execute('PRAGMA user_version').fetchone()
    listing = self.dump()
    # upgrade entry listing
    while True:
      cfg = upgrade[f'upgrade_{user_version}'](listing)
      if cfg is not None: break
      user_version += 1
    # initialise mirror root and load entry listing
    initial(mirror,cfg,user_version,preserve).load(listing)
    return json.dumps({'transferred':len(listing)}),{'Content-Type':'text/json'}

#======================================================================================================================
class XposeInit (XposeBase,CGIMixin):
#======================================================================================================================

  def do_get(self):
    upgrader = self.root/'upgrader.py'
    upgrade = {}; exec(upgrader.read_text(),upgrade)
    cfg = upgrade['initial']()
    initial(self.root,cfg,preserve=(upgrader,))
    (self.root/'shadow').mkdir()
    (self.root/'shadow'/'cats').symlink_to(cfg.cats)
    return '{}',{'Content-Type':'text/json'}

#======================================================================================================================
def initial(path,cfg,user_version=0,preserve=()):
#======================================================================================================================
  for f in path.iterdir():
    if f in preserve: continue
    if not f.is_symlink() and f.is_dir(): shutil.rmtree(f)
    else: f.unlink()
  (path/'.htaccess').write_text('<FilesMatch ".*\\.db$">\nRequire all denied\n</FilesMatch>')
  (path/'attach').mkdir();(path/'attach'/'.uploaded').mkdir()
  cats = path/'cats'
  if cats.exists(): cats.unlink(); cats.symlink_to(cfg.cats)
  else: shutil.copytree(cfg.cats,cats,symlinks=True)
  (path/'.config').mkdir()
  set_config(path/'.config',**cfg.setup(path))
  xpose = get_config(path/'.config','manage')
  with xpose.connect() as conn:
    conn.executescript(XposeSchema)
    conn.execute(f'PRAGMA user_version = {user_version}')
  xpose.cats.initial(xpose=xpose)
  return xpose
