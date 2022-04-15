# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: misc utilities
#

import sys,os,json,re
from pathlib import Path
from functools import cached_property, singledispatch
from datetime import datetime
from http import HTTPStatus
from urllib.parse import parse_qsl,urljoin
from typing import Union, Callable, Dict, Any

#======================================================================================================================
class CGIMixin:
  r"""
A simple helper mixin that simplifies writing CGI resource classes. A resource class needs only define methods :meth:`do_get`, :meth:`do_put` etc. with no input argument and output as a pair of a content string and a header dictionary.
  """
#======================================================================================================================

#----------------------------------------------------------------------------------------------------------------------
  def process_cgi(self):
#----------------------------------------------------------------------------------------------------------------------
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

  @staticmethod
  def from_server_root(path:Path)->Path:
    return Path('/'+str(path.relative_to(os.environ['DOCUMENT_ROOT'])))

  @staticmethod
  def parse_input(mime:str='application/json',chunk:int=None):
    def read(n):
      while n>0:
        t = sys.stdin.buffer.read(n)
        m = len(t)
        if m == 0: raise EOFError()
        yield t
        n -= m
    def chunk_read(n):
      while n>0:
        m = min(n,chunk)
        yield from read(m)
        n -= m
    def merge(it): return b''.join(it).decode()
    assert os.environ['CONTENT_TYPE'].startswith(mime)
    n = int(os.environ['CONTENT_LENGTH'])
    Transf = {
      'application/json': (lambda it: json.loads(merge(it))),
      'application/x-www-form-urlencoded': (lambda it: dict(parse_qsl(merge(it)))), # unsophisticated: no multiple values per key
      'application/octet-stream': (lambda it: it),
    }
    return Transf[mime]((read if chunk is None else chunk_read)(n) if n>0 else None)

  @staticmethod
  def parse_qsl()->dict[str,str]:
    return dict(parse_qsl(os.environ['QUERY_STRING']))

#======================================================================================================================
class IntStrConverter:
  r"""
An instance of this class is a bijection between the interval of whole numbers from 0 (inclusive) to 0x100000 (exclusive) and the set of strings of length 4 of characters in *symbols*. Suitable for defining attachment paths. Example::

   c = IntStrConverter() # all parameters are initialised randomly
   L = list(range(0x100000))
   assert [c.str2int(s) for s in [c.int2str(n) for n in L]] == L

:param shift: any integer
:param perm: a permutation of (0,...,19)
:param symbols: a string of length 32 where each character occurs only once
  """
#======================================================================================================================
  shift : int
  perm : tuple[int,...]
  symbols : dict[str,str]
  perm_: tuple[int,...] # inverse of perm
  symbols_: dict[str,str] # inverse of symbols

  def __init__(self,shift:int=None,perm:tuple[int,...]=None,symbols:str=None):
    from random import randint, shuffle
    from string import ascii_letters, digits
    if shift is None: shift = randint(0,0x100000)
    else: assert isinstance(shift,int)
    if perm is None: p = list(range(20)); shuffle(p); perm = tuple(p)
    else: assert set(perm) == set(range(20))
    if symbols is None: s = list(digits+ascii_letters); shuffle(s); symbols = ''.join(s[:32])
    else: assert isinstance(symbols,str) and len(symbols) == 32 and len(set(symbols)) == 32
    self.shift,self.perm = shift,perm
    self.perm_ = tuple(self.perm.index(i) for i in range(20))
    bs = [f'{i:05b}' for i in range(32)]
    self.symbols = dict(zip(bs,symbols))
    self.symbols_ = dict(zip(symbols,bs))

#----------------------------------------------------------------------------------------------------------------------
  def int2str(self,n:int)->str:
    r""":param n: value to convert"""
#----------------------------------------------------------------------------------------------------------------------
    #assert isinstance(n,int) and 0 <= n < 0x100000
    n = (n+self.shift)%0x100000 # shift: 20-bit-int -> 20-bit-int
    x = f'{n:020b}' # convert: 20-bit-int -> 20-bit-str
    x = ''.join(x[i] for i in self.perm) # permute: 20-bit-str -> 20-bit-str
    return ''.join(self.symbols[x[i:i+5]] for i in range(0,20,5)) # segment: 20-bit-str -> 4-symbol-str

#----------------------------------------------------------------------------------------------------------------------
  def str2int(self,x:str)->int:
    r""":param x: value to convert"""
#----------------------------------------------------------------------------------------------------------------------
    #assert isinstance(x,str) and len(x)==4 and all(u in self.symbols_ for u in x)
    x = ''.join(self.symbols_[u] for u in x) # segment: 4-symbol-str -> 20-bit-str
    x = ''.join(x[i] for i in self.perm_) # permute: 20-bit-str -> 20-bit-str
    n = int(x,2) # convert: 20-bit-str -> 20-bit-int
    return (n-self.shift)%0x100000 # shift: 20-bit-int -> 20-bit-int


#======================================================================================================================
class Backup:
  r"""
An instance of this class creates a context allowing transactional operations on the first level of a directory (called the root).
A subdirectory of the root must be named, and will be used for backup. It should only be used for that purpose.
The only allowed transactional operations take a single name (with no path separator) as input and move the file (or sub-directory) corresponding to that name from the root directory (if it exists) into the backup directory.
If the context exits with an exception, all the files and directories affected by the transactional operations are restored, erasing new ones if needed.
  """
#======================================================================================================================
  def __init__(self,p:Union[str,Path],name:str='.backup'):
    self.root = Path(p).resolve()
    assert self.root.is_dir() and len(Path(name).parts) == 1, (p,name)
    self.backup = self.root/name
  def __enter__(self):
    self._clear(self.backup) # just in case (e.g. crash), normally absent
    self.backup.mkdir()
    self.backup_log = []
    return self
  def __exit__(self,type,*a):
    if type is not None:
      for f,f_bak in self.backup_log: # restore
        self._clear(f)
        if f_bak is not None: f_bak.rename(f)
      self.backup.rmdir() # normally empty after restore
    else: self._clear(self.backup)
  def __call__(self,name:str):
    assert len(Path(name).parts) == 1 and name != self.backup.name # :-)
    f = self.root/name
    if f.exists(): f_bak = self.backup/name; f.rename(f_bak)
    else: f_bak = None
    self.backup_log.append((f,f_bak))
    return f
  @staticmethod
  def _clear(f:Path):
    from shutil import rmtree
    if f.is_symlink(): f.unlink()
    elif f.is_dir(): rmtree(f)
    else: f.unlink(missing_ok=True)

#======================================================================================================================
# Miscellaneous
#======================================================================================================================

class HTTPException (Exception):
  def __init__(self,status:HTTPStatus): self.status = status
def http_raise(status): raise HTTPException(status)
def http_ts(ts:float)->str: return datetime.utcfromtimestamp(ts).strftime('%a, %d %b %Y %H:%M:%S GMT')

def set_config(path,**ka):
  from dill import dump
  for key,cfg in ka.items():
    with (Path(path)/key).with_suffix('.pk').open('wb') as v: dump(cfg,v)
def get_config(path,key):
  from dill import load
  with (Path(path)/key).with_suffix('.pk').open('rb') as u: cfg = load(u)
  return cfg

class str_md(str): pass  # to identify Markdown strings
@singledispatch
def rebase(x,base): return urljoin(base,x)
@rebase.register(str_md)
def _(x,base,pat=re.compile(r'(\[.*?])\((.*?)( .*?)?\)')):
  return pat.sub((lambda m: f'{m.group(1)}({urljoin(base,m.group(2))}{m.group(3) or ""})'),x)
