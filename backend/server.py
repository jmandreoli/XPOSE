# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: instance management operations
#
import sys,sqlite3,shutil,json,traceback
from pathlib import Path
from typing import Union, Callable, Any, Optional
from . import XposeBase, WithCatsMixin
from .attach import WithAttachMixin
from .utils import CGIMixin,Backup,http_raise,http_ts,set_config,get_config

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

RoutingCode = f'''#!{sys.executable}
from os import environ, umask
from http.cookies import SimpleCookie
from pathlib import Path
from xpose import get_config
umask(0o7)
variant = '.' if (morsel:=SimpleCookie(environ.get('HTTP_COOKIE','')).get('xpose-variant')) is None else morsel.coded_value
path = Path(__file__).resolve().parent/variant
get_config(path/'.routes',environ['PATH_INFO'][1:]).setup(path).process_cgi()'''

#======================================================================================================================
class XposeServer (XposeBase,WithCatsMixin,WithAttachMixin,CGIMixin):
  r"""
An instance of this class is a CGI resource managing a whole Xpose instance.

:param authoriser: callable taking as input an access level and a path, and restricting access to that path to that level
:param attach_namer: callable taking as input a whole number and returning a string suitable as a path name (no conflict)
  """
#======================================================================================================================

  def __init__(self,authoriser:Callable[[str,Union[str,Path]],None]=None,attach_namer:Callable[[int],str]=None):
    self.authoriser = authoriser
    self.attach_namer = attach_namer

#----------------------------------------------------------------------------------------------------------------------
  def load(self,contents:Union[list,str,Path],with_oid:bool=False):
    r"""
Loads some entries in the index database. Entries are validated, and behaviour is transactional. If *with_oid* is :const:`True` (resp. :const:`False`), the entries must have (resp. must not have) an ``oid`` field. If present, the ``oid`` field must of course be different from any existing one (abort otherwise). Furthermore, the ``attach`` field must be either :const:`None` or a dictionary where each key is a relative path within the entry attachment folder and the value is an absolute path to be hard-linked to that local path. Note that subfolders (which cannot be hard-linked) never need to be explicitly created as attachments, as they are created as need be to store file attachments.

:param contents: the list of entries to load into the index database, or a path to a json file as obtained by method :meth:`dump`
:param with_oid: whether the entries should be stored with the oid as specified in *contents*
    """
#----------------------------------------------------------------------------------------------------------------------
    attach_info:dict[str,dict[str,str]] = {}
    def entry(row,i):
      assert set(row) == field_set, set(row)^field_set
      value = row['value']
      self.cats.validate(row['cat'],value)
      row['value'] = json.dumps(value)
      memo = row['memo']
      row['memo'] = None if memo is None else json.dumps(memo)
      a = f'{i:04x}'; a = f'{a[:2]}/{a[-2:]}' # local encoding of i
      attach_info[a] = row['attach']; row['attach'] = a
      return tuple(row[f] for f in fields)
    def create_attach(oid,a,namer=self.attach_namer,root=self.attach.root):
      a = attach_info[a]
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
    assert isinstance(with_oid,bool)
    if isinstance(contents,list): listing = contents
    else:
      with open(contents) as u: listing = json.load(u)['listing']
    with self.connect() as conn:
      conn.row_factory = sqlite3.Row
      conn.create_function('create_attach',2,create_attach) # different from the default
      conn.create_function('authoriser',2,(lambda access,attach,auth=self.authoriser,root=self.attach.root: auth(access,root/attach)))
      cur = conn.execute('PRAGMA table_info(Entry)'); fields = [x['name'] for x in cur]; cur.close()
      if with_oid is False: fields.remove('oid')
      field_set = set(fields)
      sql = f'INSERT INTO Entry ({",".join(fields)}) VALUES ({",".join(len(fields)*["?"])})'
      listing = [entry(row,i) for i,row in enumerate(listing)]
      conn.executemany(sql,listing)

#----------------------------------------------------------------------------------------------------------------------
  def dump(self,path:Union[str,Path]=None,clause:str=None,with_oid:bool=False):
    r"""
Extracts a list of entries from the index database. If *with_oid* is :const:`True` (resp. :const:`False`), the entries will have (resp. not have) an ``oid`` field. Furthermore, the ``attach`` field has the same form as in :meth:`load`.

:param path: if specified, the extracted entries, with meta-data, are dumped into a json file, otherwise they are returned
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
      ts = self.index_db.stat().st_mtime
    R = {'meta':{'origin':'XposeDump','clause':clause,'with_oid':with_oid,'timestamp':ts,'root':str(self.root),'user_version':user_version},'listing':listing}
    if path is None: return R
    else:
      with open(path,'w') as v: json.dump(R,v)

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
No input expected. Three phases:

* Phase 1: real->shadow
  * when self contains "config.py" file and "shadow" directory: self is the real instance, target=shadow

* Phase 0: real->real
  * when self contains "config.py" file but not "shadow" directory: only for (re-)initialisation
  * requires only "config.py"

* Phase 2: shadow->real
  * when self contains neither "config.py" file nor "shadow" directory: self is the shadow instance, target=real (parent directory)

Main components:

* in both real and shadow instances:
  * index.db: index database file
  * attach: attachment directory
  * .routes: route directory

* in real instance:
  * config.py: symlink to readable python file containing configuration code
  * route.py: generated python file for cgi-bin script to symlink to
  * cats: fixed copy of cats directory from config, only updated in Phase 2

* in shadow instance:
  * cats: symlink to directory from config
    """
#----------------------------------------------------------------------------------------------------------------------
    from .main import XposeMain,XposeAttach
    config_ = self.root/'config.py'
    shadow_ = self.root/'shadow'
    self_is_configured = config_.exists()
    target_is_shadow = self_is_configured is True and shadow_.exists()
    if target_is_shadow is True: target = shadow_ # Phase 1
    elif self_is_configured is True: target = self.root; shadow_.mkdir() # Phase 0
    else: assert self.root.name == 'shadow'; target = self.root.parent; config_ = target/'config.py'; assert config_.exists() # Phase 2
    # retrieve configuration -> cats, routes, release, upgrades:list[]
    cfg = {}; exec(config_.read_text(),cfg)
    cats:Path = Path(cfg['cats'])
    assert cats.is_dir()
    routes:dict[str,XposeBase] = cfg.get('routes')
    routes = {} if routes is None else dict(routes)
    assert all(isinstance(x,XposeBase) for x in routes.values())
    for key,default in dict(main=XposeMain,attach=XposeAttach,manage=XposeServer).items():
      if routes.get(key) is None: routes[key] = default()
    release:int = cfg.get('release',0)
    assert isinstance(release,int) and release >= 0
    upgrades:list[Callable[[list],None]] = [cfg[f'upgrade_{n}'] for n in range(release)]
    # collect current entry listing
    if self.index_db.exists():
      dump = self.dump()
      listing = dump['listing']
      user_version = dump['meta']['user_version']
      # upgrade entries
      n_upgrades = release - user_version
      if target_is_shadow is True:
        assert n_upgrades>=0
        for upg in upgrades[user_version:]: upg(listing)
      else: assert n_upgrades==0 # forces any upgrade to go through shadow first
    else: listing = []; n_upgrades = None
    with Backup(target) as backup:
      # set cats
      cats_ = backup('cats')
      if target_is_shadow: cats_.symlink_to(cats)
      else: shutil.copytree(cats,cats_,symlinks=True)
      # set route.py
      route_ = backup('route.py')
      if not target_is_shadow: route_.write_text(RoutingCode); route_.chmod(0o750)
      # set .routes
      routes_ = backup('.routes')
      routes_.mkdir(); set_config(routes_,**routes)
      # set attach
      attach_ = backup('attach')
      attach_.mkdir();(attach_/'.uploaded').mkdir()
      # set index.db
      backup('index.db').touch() # to set correct mode
      xpose = get_config(routes_,'manage').setup(target)
      with xpose.connect() as conn:
        conn.executescript(XposeSchema)
        conn.execute(f'PRAGMA user_version = {release}')
      xpose.cats.initial(xpose=xpose)
      # load entry listing (important to keep in the same backed-up transaction as attach_)
      xpose.load(listing)
    # result
    return json.dumps({'user_version':release,'upgrades':n_upgrades}),{'Content-Type':'text/json'}
