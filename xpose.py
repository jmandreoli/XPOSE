import sys,os,sqlite3,shutil,json,re
import traceback
from functools import cached_property, singledispatch
from datetime import datetime
from pathlib import Path
if not hasattr(Path,'hardlink_to'): Path.hardlink_to = lambda self,target: Path(target).link_to(self)
from http import HTTPStatus
from urllib.parse import parse_qs, parse_qsl,urljoin
#sqlite3.register_converter('json',json.loads)

XposeSchema = '''
CREATE TABLE Entry (
  oid INTEGER PRIMARY KEY AUTOINCREMENT,
  version INTEGER NOT NULL,
  cat TEXT NOT NULL,
  value JSON NOT NULL,
  attach TEXT NULLABLE,
  created DATETIME NOT NULL,
  modified DATETIME NOT NULL
);

CREATE TRIGGER EntryAttach AFTER INSERT ON Entry
  BEGIN UPDATE Entry SET attach=oid_encoder(oid,attach) WHERE oid=NEW.oid; END;

CREATE TABLE Short (
  entry REFERENCES Entry ON DELETE CASCADE,
  value TEXT NOT NULL
);
'''

class XposeBase:

  attach_namer = None # global default, set up at the end of this file

  def __init__(self,root='.',attach_namer=None):
    self.root = root = Path(root).resolve()
    self.attach = Attach((root/'attach').resolve(),attach_namer or self.attach_namer)
    self.cats = Cats((root/'cats').resolve())
    self.index_db = (root/'index.db').resolve()

  def connect(self,**ka):
    conn = sqlite3.connect(self.index_db,**ka)
    conn.create_function('oid_encoder',2,(lambda oid,attach,c=self.attach.namer.int2str:c(oid)))
    conn.create_function('xpose_template',3,self.apply_template)
    return conn

  def apply_template(self,tmpl,args,err_tmpl):
    try: return self.cats.load_template(tmpl+'.xhtml').generate(xpose=self,**json.loads(args)).render('html')
    except: return self.cats.load_template(err_tmpl+'.xhtml').generate().render('html')

  @cached_property
  def url_base(self): return Path(os.environ['SCRIPT_NAME']).parent

  def rebase(self,x,path): return rebase(x,str(self.url_base/'attach'/path/'_'))

class CGIMixin:

  def process_cgi(self):
    method = os.environ['REQUEST_METHOD']
    do = getattr(self,'do_'+method.lower(),None)
    content,headers = '',{}
    try:
      if do is None: http_raise(HTTPStatus.NOT_IMPLEMENTED)
      else: content,headers = do()
    except Exception as e:
      import traceback
      status = e.status if isinstance(e,HTTPException) else HTTPStatus.INTERNAL_SERVER_ERROR
      headers = {'Status':f'{status.value} {status.phrase}','Content-Type':'text/plain'}
      content = traceback.format_exc()
    for k,v in headers.items(): print(f'{k}: {v}')
    print()
    print(content,flush=True)

class XposeMain (XposeBase,CGIMixin):

  sql_oid = '''SELECT oid,version,cat,Short.value as short,Entry.value as value,attach
    FROM Entry LEFT JOIN Short ON Short.entry=oid
    WHERE oid=?'''

  def do_get(self):
    """
Input is an (encoded) form with a single field "sql", which must denote an SQLite query of type "SELECT" only.
    """
    form = dict(parse_qsl(os.environ['QUERY_STRING']))
    with self.connect() as conn:
      conn.row_factory = sqlite3.Row
      if (sql:=form.get('sql')) is not None:
        sql = sql.strip()
        assert sql.lower().startswith('select ')
        resp = json.dumps([dict(r) for r in conn.execute(sql).fetchall()])
      elif (oid:=form.get('oid')) is not None:
        oid = int(oid)
        r = dict(conn.execute(self.sql_oid,(oid,)).fetchone())
        r['short'] = r['short'].replace('"',r'\"')
        resp = '{{"oid":{oid},"version":{version},"cat":"{cat}","short":"{short}","value":{value},"attach":"{attach}"}}'.format(**r)
      else: http_raise(HTTPStatus.NOT_FOUND)
    return resp, {'Content-Type':'text/json','Last-Modified':http_ts(self.index_db.stat().st_mtime)}

  def do_post(self):
    """
Input is an (encoded) form with a single field "sql", which must denote an arbitrary SQLite query
    """
    form = parse_input()
    sql = form['sql'].strip()
    with self.connect() as conn:
      c = conn.executescript(sql)
      return dict(total_changes=conn.total_change,lastrowid=c.lastrowid), {'Content-Type':'text/json'}

  def do_put(self):
    """
Input is any JSON encoded entry.
    """
    entry = parse_input('text/json')
    oid,version,value = entry.get('oid'),entry.get('version'),json.dumps(entry['value'])
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with self.connect() as conn:
      if oid is None:
        version=0
        sql = 'INSERT INTO Entry (version,cat,value,created,modified) VALUES (?,?,?,?,?)',(version+1,entry['cat'],value,now,now)
      else:
        version = int(version)
        sql = 'UPDATE Entry SET version=iif(version=?,?,NULL),value=?,modified=? WHERE oid=?',(version,version+1,value,now,int(oid))
      try: res = conn.execute(*sql)
      except sqlite3.IntegrityError: http_raise(HTTPStatus.CONFLICT)
      conn.commit()
      if oid is None: oid = res.lastrowid
      attach,short = conn.execute('SELECT attach,Short.value FROM Entry,Short WHERE Short.entry=? AND oid=?',(oid,oid)).fetchone()
    return json.dumps({'oid':oid,'version':version+1,'short':short,'attach':attach}), {'Content-Type':'text/json'}

  def do_delete(self):
    """
Input is an (encoded) form with a single field "oid", which must denote the primary key of an Entry.
    """
    form = parse_input()
    oid = int(form['oid'])
    with self.connect() as conn:
      conn.execute('PRAGMA foreign_keys = ON')
      conn.execute('DELETE FROM Entry WHERE oid=?',(oid,))
      conn.commit()
    try: self.attach.rm(self.attach.namer.int2str(oid))
    except FileNotFoundError: pass
    return json.dumps({'oid':oid}), {'Content-Type':'text/json'}

  def do_head(self):
    return 'héllo world', {'Content-Type':'text/plain; charset=UTF-8'}

class XposeAttach (XposeBase,CGIMixin):

  def __init__(self,umask=0o2,chunk=0x100000,**ka):
    os.umask(umask)
    self.chunk = chunk
    super().__init__(**ka)

  def do_get(self):
    """
Input is an (encoded) form with a single field "path".
    """
    form = dict(parse_qsl(os.environ['QUERY_STRING']))
    path,level = self.attach.getpath(form['path'])
    content = self.attach.ls(path)
    return json.dumps({'content':content,'version':self.version(path),'toplevel':level==0}),{'Content-Type':'text/json'}

  def do_put(self):
    """
Input is a JSON encoded list of pairs of filenames.
    """
    content = parse_input('text/json')
    path,version,ops = content['path'],content['version'],content['ops']
    with self.connect(isolation_level='IMMEDIATE'): # only to ensure isolation
      path,level = self.attach.getpath(path)
      if self.version(path) != version: http_raise(HTTPStatus.CONFLICT)
      errors = [err for op in ops if (err:=self.attach.do(path,op['src'].strip(),op['trg'].strip(),bool(op['is_new']))) is not None]
      content = self.attach.ls(path)
      version = self.version(path)
    return json.dumps({'content':content,'version':version,'toplevel':level==0,'errors':errors}), {'Content-Type':'text/json'}

  def do_post(self):
    """
Input is an octet stream.
    """
    form = dict(parse_qsl(os.environ['QUERY_STRING']))
    target = form.get('target')
    assert os.environ['CONTENT_TYPE'] == 'application/octet-stream'
    res = self.attach.upload(sys.stdin.buffer,int(os.environ['CONTENT_LENGTH']),target,chunk=self.chunk)
    content = dict(zip(('name','mtime','size'),res))
    return json.dumps(content), {'Content-Type':'text/json'}

  @staticmethod
  def version(path):
    if path.exists():
      s = path.stat()
      return [s.st_ino,s.st_mtime]
    else: return None

class XposeServer (XposeBase):

  EventSchema = '''
CREATE TABLE Event (
  entry REFERENCES Entry ON DELETE CASCADE,
  start DATETIME NOT NULL,
  end DATETIME NOT NULL,
  title TEXT NOT NULL,
  source TEXT NOT NULL,
  path TEXT NOT NULL
);

CREATE INDEX EventIndexSource ON Event (source);

CREATE INDEX EventIndexStart ON Event (start DESC);
  '''

  def initial(self,script=None):
    assert self.root.is_dir()
    p = self.cats.root
    assert p.is_dir() and (p/'.visible.json').is_file()
    p = self.attach.root
    assert p.is_dir() and (p/'.uploaded').is_dir()
    p = self.index_db
    assert p.is_file()
    if p.stat().st_size==0:
      with self.connect() as conn:
        conn.executescript(XposeSchema)
        if script is not None: conn.executescript(script)
        for cat in self.cats: self.cats[cat].initial(self)
    return self

  def load(self,content,with_oid=False):
    def get_fields(conn):
      cur = conn.execute('PRAGMA table_info(Entry)')
      n, = (n for n,d in enumerate(cur.description) if d[0]=='name')
      fields = [x[n] for x in cur]
      cur.close()
      return fields
    def entry(row,i):
      assert set(row) == field_set, set(row)^field_set
      value = row['value']
      self.cats[row['cat']].validator.validate(value)
      row['value'] = json.dumps(value)
      a = f'{i:04x}'; a = f'{a[:2]}/{a[2:]}' # arbitrary 1-1 encoding of i
      Info[a] = row['attach']; row['attach'] = a
      return tuple(row[f] for f in fields)
    def oid_encoder(oid,a,enc=self.attach.namer.int2str):
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
      with Path(content).open() as u: listing = json.load(u)['listing']
    with self.connect() as conn:
      conn.create_function('oid_encoder',2,oid_encoder) # overrides the default
      fields = get_fields(conn)
      if not with_oid: fields.remove('oid')
      field_set = set(fields)
      sql = f'INSERT INTO Entry ({",".join(fields)}) VALUES ({",".join(len(fields)*["?"])})'
      Info = {}
      listing = [entry(row,i) for i,row in enumerate(listing)]
      conn.executemany(sql,listing)
      conn.commit()

  def dump(self,path=None,where=None,with_oid=False):
    def trans(row):
      row = dict(row)
      if not with_oid: del row['oid']
      p = self.attach.root/row['attach']
      row['attach'] = dict((str(f.relative_to(p)),str(f)) for f in p.glob('**/*') if not f.is_dir()) or None
      row['value'] = json.loads(row['value'])
      return row
    where_ = '' if where is None else f' WHERE {where}'
    with self.connect() as conn:
      conn.row_factory = sqlite3.Row
      listing = list(map(trans,conn.execute(f'SELECT * FROM Entry{where_}').fetchall()))
      ts = datetime.now().isoformat(timespec='seconds')
    if path is None: return listing
    path = Path(path)
    with path.open('w') as v:
      json.dump({'meta':{'origin':'XposeDump','timestamp':ts,'root':str(self.root),'where':where},'listing':listing},v,indent=1)

  def precompute_trigger(self,table,cat,defn,when=None):
    """
Declares a trigger which can be used in a cat specific configuration
    """
    def create_trigger(op,delete):
      return f'''
CREATE TRIGGER {table}Trigger{op.split(' ',1)[0].title()}{''.join(z.title() for z in cat.split('/'))}{when_}
AFTER {op} ON Entry WHEN NEW.cat='{cat}'{when}
BEGIN
  {delete}INSERT INTO {table}
{defn};
END'''
    defn = '\n'.join(f'    {x}' for x in defn.split('\n') if x.strip())
    when,when_ = ('','') if when is None else (f' AND {when}',hex(sum(ord(x) for x in when))[2:])
    script = ';\n'.join(create_trigger(*x) for x in (('INSERT',''),('UPDATE OF value',f'DELETE FROM {table} WHERE entry=OLD.oid;\n  ')))
    with self.connect() as conn: conn.executescript(script)

class Attach:

  def __init__(self,root,namer): self.root,self.namer = root,namer

  def getpath(self,path):
    path = (self.root/path).resolve()
    level = len(path.relative_to(self.root).parts)-2
    assert level>=0
    return path,level

  def ls(self,path):
    def E(p): s = p.stat(); return p.is_dir(),p.name,datetime.fromtimestamp(s.st_mtime).isoformat(timespec='seconds'),(s.st_size if p.is_file() else -len(list(p.iterdir())))
    if not path.is_dir(): return []
    content = L = sorted(map(E,path.iterdir()))
    while not L:
      path.rmdir()
      path = path.parent
      if path==self.root: break
      L = list(path.iterdir())
    return [x[1:] for x in content]

  def do(self,path,src,trg,is_new):
    def relative_to(p1,p2):
      try: return p if (p:=p1.relative_to(p2)).parts[0]!='.' else None
      except ValueError: return None
    # checks that path,src,trg always point within self.root even when they may be absolute or contain ..
    base = self.root/'.uploaded' if is_new else path
    src = (base/src).resolve()
    assert (src_r:=relative_to(src,base)) is not None and len(src_r.parts)==1
    if not src.exists(): return f'NotFound(src):{src}'
    if trg=='':
      if src.is_dir(): shutil.rmtree(src)
      else: src.unlink()
    else:
      trg = (path/trg).resolve()
      if (trg_r:=relative_to(trg,self.root)) is None or trg_r.parts[:2] != path.relative_to(self.root).parts[:2]: return f'Invalid(trg):{trg}'
      if trg.exists(): return f'AlreadyExists(trg):{trg}'
      trg.parent.mkdir(parents=True,exist_ok=True)
      src.rename(trg)

  def rm(self,path): shutil.rmtree(self.root/path)

  def upload(self,buf,size,target,chunk):
    from tempfile import NamedTemporaryFile
    upload_dir = self.root/'.uploaded'
    if size==0: (upload_dir/target).unlink(); return
    with ((upload_dir/target).open('ab') if target else NamedTemporaryFile('wb',dir=upload_dir,prefix='',delete=False)) as v:
      f = Path(v.name)
      try:
        while size>0:
          m = n = min(size,chunk)
          while m>0:
            t = buf.read(m); m_ = len(t)
            if m_==0: raise EOFError()
            v.write(t); m -= m_
          size -= n
      except: f.unlink(); raise
    s = f.stat()
    return f.name,datetime.fromtimestamp(s.st_mtime).isoformat(timespec='seconds'),s.st_size

class Cats:
  def __init__(self,root): self.root = root.resolve()
  @cached_property
  def template_loader(self):
    from genshi.template import TemplateLoader
    return TemplateLoader(str(self.root/'templates'),auto_reload=True)
  def load_template(self,tmpl): return self.template_loader.load(tmpl)
  @cached_property
  def contents(self):
    with (self.root/'.visible.json').open() as u: return dict((cat,None) for cat in json.load(u))
  def __iter__(self): yield from self.contents
  def __getitem__(self,cat):
    c = self.contents[cat]
    if c is None: self.contents[cat] = c = Cat(cat,self.root)
    return c

class Cat:

  def __init__(self,name,root):
    self.name,self.root = name,root
    p = root/'utils'/name
    cfg = {'__file__':p}
    exec(p.with_suffix('.py').read_text(),cfg)
    self.__dict__.update((k,v) for k,v in cfg.items() if not k.startswith('__'))

  @cached_property
  def validator(self):
    from jsonschema import Draft202012Validator,RefResolver
    p = self.root/'jschemas'/self.name
    with p.with_suffix('.json').open() as u: schema = json.load(u)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema=schema).evolve(resolver=RefResolver(f'file://{self.root}/jschemas/_',{}))

class HTTPException (Exception):
  def __init__(self,status): self.status = status
def http_raise(status): raise HTTPException(status)
def http_ts(ts): return datetime.utcfromtimestamp(ts).strftime('%a, %d %b %Y %H:%M:%S GMT')

def parse_input(t='application/x-www-form-urlencoded',transf=True):
  assert os.environ['CONTENT_TYPE'].startswith(t)
  n = int(os.environ['CONTENT_LENGTH'])
  x = sys.stdin.read(n)
  if transf:
    if t == 'application/x-www-form-urlencoded': x = dict(parse_qsl(x))
    elif t == 'text/json': x = json.loads(x)
  return x

class str_md(str): pass  # to identify Markdown strings
@singledispatch
def rebase(x,base): return urljoin(base,x)
@rebase.register(str_md)
def _(x,base,pat=re.compile(r'(\[.*?\])\((.*?)( .*?)?\)')):
  return pat.sub((lambda m: f'{m.group(1)}({urljoin(base,m.group(2))}{m.group(3) or ""})'),x)

class IntStrConverter:
  shift : int # any integer
  perm : tuple # must be permutation of range(0,20)
  symbols : str # must be of length 32 with all distinct characters

  def __init__(self,shift=None,perm=None,symbols=None,check=False):
    from random import randint, shuffle
    from string import ascii_uppercase, digits
    if shift is None: shift = randint(0,0x100000)
    elif check: assert isinstance(shift,int)
    self.shift = shift
    if perm is None: perm = list(range(20)); shuffle(perm)
    elif check: assert len(perm)==20 and list(set(perm)) == list(range(20))
    self.perm = perm
    self.perm_ = tuple(perm.index(i) for i in range(20))
    if symbols is None: symbols = (digits+ascii_uppercase)[:32]
    elif check: assert isinstance(symbols,str) and len(symbols) == 32 and len(set(symbols)) == 32
    self.symbols = symbols
    self.symbol_ = dict((c,f'{i:05b}') for i,c in enumerate(symbols))

  def int2str(self,n:int)->str:
    #assert n < 0x100000
    n = (n+self.shift)%0x100000 # shift
    x = f'{n:020b}' # 20-digit binary
    x = ''.join(x[i] for i in self.perm) # permute the bits
    x = ''.join(self.symbols[int(x[i:i+5],2)] for i in range(0,20,5))
    return f'{x[:2]}/{x[2:]}'

  def str2int(self,x:str)->int:
    #assert len(x)==5 and x[2] == '/'
    x = ''.join(self.symbol_[u] for t in x.split('/',2) for u in t)
    x = ''.join(x[i] for i in self.perm_)
    n = int(x,2)
    return (n-self.shift)%0x100000

# Beware: if you change this line, all the current oid encodings will be fucked up
XposeBase.attach_namer = IntStrConverter(shift=0xe1e06,perm=(17,12,9,6,11,14,0,4,19,8,1,18,3,7,5,16,10,2,15,13))
