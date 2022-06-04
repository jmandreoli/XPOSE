# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: instance management
#

import sys,sqlite3,shutil,json
from pathlib import Path
from typing import Callable, Any, Optional
from . import XposeBase, WithCatsMixin
from .attach import WithAttachMixin
from .utils import CGIMixin,Backup,http_raise,http_ts,set_config,get_config,default_attach_namer

XposeSchema = '''
CREATE TABLE Entry (
  oid INTEGER PRIMARY KEY AUTOINCREMENT,
  version INTEGER NOT NULL,
  cat TEXT NOT NULL,
  value TEXT NOT NULL, -- JSON
  attach TEXT NULLABLE,
  created DATETIME NOT NULL,
  modified DATETIME NOT NULL,
  access TEXT NULLABLE,
  memo TEXT NULLABLE -- JSON
);

CREATE TRIGGER EntryTriggerInsert AFTER INSERT ON Entry
  BEGIN UPDATE Entry SET attach=create_attach(oid) WHERE oid=NEW.oid; END;
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

CREATE VIEW EntryFull AS -- Use only with detect_types=sqlite3.PARSE_COLNAMES
  SELECT version,cat,value AS "value [JSON]",attach AS "attach [ATTACH]",created,modified,access,memo AS "memo [JSON]" FROM Entry;

CREATE VIEW EntryShort AS
  SELECT oid,version,cat,Entry.value AS value,attach,created,modified,access,memo,Short.value AS short FROM Entry LEFT JOIN Short ON Short.entry=oid;
'''

RoutingCode = f'''#!{sys.executable}
from os import environ, umask
from http.cookies import SimpleCookie
from pathlib import Path
from {__package__} import get_config
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

  def __init__(self,authoriser:Callable[[str,Path],None]=(lambda level,path: None),attach_namer:Callable[[int],str]=default_attach_namer):
    self.authoriser = authoriser
    self.attach_namer = attach_namer

#----------------------------------------------------------------------------------------------------------------------
  def dump(self,meta:Optional[dict[str,Optional[str]]]=None,**queries)->dict[str,Any]:
    r"""
Executes a batch of SQL queries (SELECT only) specified by *queries* (key-value pairs are label-query pairs). Returns a dictionary with the same keys and values set to the results of the queries. The dictionary *meta* holds a description of the batch. It is augmented with details about the execution, and added to the result under key ``meta``.

Table (view) ``EntryFull`` can be used in queries instead of ``Entry`` to produce listings suitable for method :meth:`load` (field ``attach`` is converted appropriately). In particular, when *queries* is empty, it is replaced by::

   {'listing':'SELECT * FROM EntryFull'}
    """
#----------------------------------------------------------------------------------------------------------------------
    def attach_contents(attach,root=self.attach.root):
      p = root/attach.decode() # sqlite converters' arguments are always bytes
      return dict((str(f.relative_to(p)),str(f)) for f in p.glob('**/*') if not f.is_dir()) or None
    sqlite3.register_converter('ATTACH',attach_contents)
    queries_:dict[str,str] = dict(queries) or {'listing':'SELECT * FROM EntryFull'}
    with self.connect(detect_types=sqlite3.PARSE_COLNAMES,isolation_level='IMMEDIATE') as conn:
      conn.row_factory = sqlite3.Row
      R:dict[str,Any] = {label:[dict(r) for r in conn.execute(sql)] for label,sql in queries_.items()}
      user_version, = conn.execute('PRAGMA user_version').fetchone()
      R['meta'] = {'root':str(self.root),'ts':self.index_db.stat().st_mtime,'user_version':user_version,**(meta or {})}
    return R

#----------------------------------------------------------------------------------------------------------------------
  def load(self,listing:list):
    r"""
Loads some entries in the index database. Entries are validated, and behaviour is transactional. The ``attach`` field in each *listing* entry must be either :const:`None` or a dictionary where each key is a relative path within the entry attachment directory and the value is an absolute path to be hard-linked to that local path. Note that sub-directories (which cannot be hard-linked) never need to be explicitly created as attachments, as they are created as need be to store file attachments.

:param listing: the list of entries to load into the index database
    """
#----------------------------------------------------------------------------------------------------------------------
    if not listing: return
    with self.connect() as conn:
      conn.row_factory = sqlite3.Row
      fields = tuple(field for r in conn.execute('PRAGMA table_info(Entry)') if (field:=r['name'])!='oid')
    def entry(row,fields=fields,field_set=frozenset(fields)):
      assert set(row) == field_set, set(row)^field_set
      self.cats.validate(row['cat'],row['value'])
      contents = row['attach']; row['attach'] = None
      return tuple(row[f] for f in fields),contents
    listing_,contents_ = zip(*map(entry,listing))
    def create_attach(oid,namer=self.attach_namer,root=self.attach.root,contents_=iter(contents_)):
      attach = namer(oid)
      contents = next(contents_)
      if contents is not None:
        p = root/attach
        for name,src in contents.items():
          if name=='.htaccess': continue # top-level access control is handled elsewhere
          trg = p/name
          trg.parent.mkdir(parents=True,exist_ok=True)
          trg.hardlink_to(src)
      return attach
    with self.connect(isolation_level='IMMEDIATE') as conn:
      conn.create_function('create_attach',1,create_attach,deterministic=True)
      conn.create_function('authoriser',2,(lambda access,attach,auth=self.authoriser,root=self.attach.root: auth(access,root/attach)),deterministic=True)
      sql = f'INSERT INTO Entry ({",".join(fields)}) VALUES ({",".join(len(fields)*["?"])})'
      conn.executemany(sql,listing_)

#----------------------------------------------------------------------------------------------------------------------
  def precompute_trigger(self,table:str,cat:str,defn:str,when:Optional[str]=None):
    r"""
Declares a trigger after ``INSERT`` and ``UPDATE`` operations on the ``Entry`` table, when the ``cat`` field is *cat*. The triggered action must be an insertion into *table*. Suppose for example that a category ``meeting`` specifies, in its json schema, an attribute ``title`` and ``setting``, itself with attributes ``date`` and ``time``. We could have:

.. code-block:: python

   title = 'json_extract(NEW.value,"$.title")'
   date = 'json_extract(NEW.value,"$.setting.date")'
   time = 'json_extract(NEW.value,"$.setting.time")'
   defn = f'VALUES NEW.oid,format("%s [%s at %s]",{title},{date},{time})'
   precompute_trigger('Short','meeting',defn)

The resulting triggers are:

.. code-block:: sql

   CREATE TRIGGER ShortTriggerInsertMeeting AFTER INSERT ON Entry WHEN NEW.cat="meeting"
   BEGIN INSERT INTO Short VALUES NEW.oid,format("%s [%s at %s]",json_extract(NEW.value,"$.title"),json_extract(NEW.value,"$.setting.date"),json_extract(NEW.value,"$.setting.time")); END;
   CREATE TRIGGER ShortTriggerUpdateMeeting AFTER UPDATE ON Entry WHEN NEW.cat="meeting"
   BEGIN INSERT INTO Short VALUES NEW.oid,format("%s [%s at %s]",json_extract(NEW.value,"$.title"),json_extract(NEW.value,"$.setting.date"),json_extract(NEW.value,"$.setting.time")); END

:param table: the target table populated by the trigger
:param cat: the category (field ``cat``) for which the trigger executes
:param when: (optional) additional condition for the trigger to execute
:param defn: what to insert into the target table, as an SQL ``SELECT`` statement or ``VALUES`` clause
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
  def do_get(self):
    r"""
Input: url-encoded form where each field specifies a label-query pair, passed to method :meth:`dump`.

Output (text/json): output of method :meth:`dump`.
    """
#----------------------------------------------------------------------------------------------------------------------
    form = self.parse_qsl()
    meta = {'source':form.pop('meta','XposeDump')} # meta field could carry json encoded dict rather than just source name
    resp = self.dump(meta,**form)
    return json.dumps(resp,indent=1),{'Content-Type':'text/json','Content-Disposition':'attachment; filename="xpose-dump.json"','Last-Modified':http_ts(resp['meta']['ts'])}

#----------------------------------------------------------------------------------------------------------------------
  def do_post(self):
    r"""
No input expected. Two phases:

* Phase 1: when the root contains a ``config.py`` file, transfer [real->shadow] *self* is the real instance, *target* is ``./shadow`` from root.
* Phase 2: when the root does not contain a ``config.py`` file, transfer [shadow->real] *self* is the shadow instance (must be named ``shadow``), *target* is ``..`` from root.
    """
#----------------------------------------------------------------------------------------------------------------------
    config = self.root/'config.py'
    target_is_shadow = config.exists()
    if target_is_shadow is True: target = self.root/'shadow'; target.mkdir(exist_ok=True) # Phase 1
    else: assert self.root.name == 'shadow'; target = self.root.parent; config = target/'config.py' # Phase 2
    release,n_upgrades,n_loaded = initial(config,target,target_is_shadow,self.dump())
    return json.dumps({'data-release':release,'upgrades':n_upgrades,'loaded':n_loaded}),{'Content-Type':'text/json'}

#----------------------------------------------------------------------------------------------------------------------
  def do_put(self):
    r"""
Input: JSON formatted dump from another Xpose instance (or :const:`None`).
    """
#----------------------------------------------------------------------------------------------------------------------
    dump = self.parse_input()
    config = self.root/'config.py'
    release,n_upgrades,n_loaded = initial(config,self.root,False,dump)
    return json.dumps({'data-release':release,'upgrades':n_upgrades,'loaded':n_loaded}),{'Content-Type':'text/json'}

#----------------------------------------------------------------------------------------------------------------------
def initial(config:Path,target:Path,target_is_shadow:bool,dump:Optional[dict]):
  r"""
Initialises an Xpose instance.

:param config: path to config file
:param target: path to directory to initialise
:param target_is_shadow: whether *target* is a shadow directory
:param dump: dump of an existing instance (as obtained by method :meth:`dump`)
  """
#----------------------------------------------------------------------------------------------------------------------
  from .main import XposeMain,XposeAttach
  # retrieve configuration -> cats, routes, release, upgrades
  assert config.is_file()
  cfg:dict[str,Any] = {}; exec(config.read_text(),cfg)
  cats:Path = Path(cfg['cats'])
  assert cats.is_dir()
  routes:dict[str,XposeBase] = {} if (r:=cfg.get('routes')) is None else dict(r)
  assert all(isinstance(x,XposeBase) for x in routes.values())
  for key,default in ('main',XposeMain),('attach',XposeAttach),('manage',XposeServer):
    if routes.get(key) is None: routes[key] = default()
  release:int = cfg.get('release',0)
  assert isinstance(release,int) and release >= 0
  upgrades:list[Callable[[list],None]] = [cfg[f'upgrade_{n}'] for n in range(release)]
  # collect current entry listing
  if dump is None: listing = n_upgrades = n_loaded = None
  else:
    listing = dump['listing']
    user_version = dump['meta']['user_version']
    # upgrade entries
    n_upgrades = release - user_version
    if target_is_shadow is True:
      assert n_upgrades>=0
      for upg in upgrades[user_version:]: upg(listing)
    else: assert n_upgrades==0 # forces any upgrade to go through shadow first
    n_loaded = len(listing)
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
    # load entry listing
    if listing is not None: xpose.load(listing)
  # result
  return release,n_upgrades,n_loaded
