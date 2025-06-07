# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: misc utilities
#

import sys,os,json,re
from pathlib import Path
from contextlib import contextmanager
from functools import singledispatch
from datetime import datetime, UTC
from http import HTTPStatus
from urllib.parse import parse_qsl,urljoin
from typing import Optional

#======================================================================================================================
class CGIMixin:
  r"""
A simple helper mixin that simplifies writing CGI resource classes. A resource class needs only define methods :meth:`do_get`, :meth:`do_put` etc. with no input argument and output as a pair of a content string and a header dictionary.
  """
#======================================================================================================================

#----------------------------------------------------------------------------------------------------------------------
  def process_cgi(self):
    r"""
Selects and executes the ``do_*`` method of this resource. Catches all exceptions and return them as plain text with the appropriate HTTP status code (500 by default) and traceback as body.
    """
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

#----------------------------------------------------------------------------------------------------------------------
  @staticmethod
  def parse_input(mime:str='application/json',chunk:int=None):
    r"""
Parses input stream according to *mime*:

* ``application/json``: applies json parser
* ``application/x-www-form-urlencoded``: returns a dictionary (unsophisticated: no multiple values per key)
* ``application/octet-stream``: returns an iterator of byte strings

:param mime: the mimetype to interpret the input
:param chunk: never reads more than this amount of bytes (if not :const:`None`)
    """
#----------------------------------------------------------------------------------------------------------------------
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
      'application/x-www-form-urlencoded': (lambda it: dict(parse_qsl(merge(it)))),
      'application/octet-stream': (lambda it: it),
    }
    return Transf[mime]((read if chunk is None else chunk_read)(n) if n>0 else None)

  @staticmethod
  def parse_qsl()->dict[str,str]:
    return dict(parse_qsl(os.environ['QUERY_STRING']))

#======================================================================================================================
class IntStrConverter:
  r"""
An instance of this class is a bijection between the interval of whole numbers :math:`\{0\cdots2^D{-}1\}` and the set of strings of length :math:`K=\frac{D}{P}` of characters in *symbols*, which must be a string of length :math:`2^P` with no repetition. Example with all default parameters (where :math:`D=20,P=5,K=4`)::

   c = IntStrConverter() # all default parameters
   assert all(c.str2int(c.int2str(n))==n for n in range(c.bound+1))

:param symbols: a string with no repetition, clipped to have a size of the form :math:`2^P` (default: random string of size :math:`32`)
:param perm: a permutation of (:math:`0,\cdots,D-1`) or the integer :math:`K` (permutation randomly generated with :math:`D=KP`)
:param shift: a non negative integer (default: random)
  """
#======================================================================================================================
  symbols : dict[str,str]
  perm : tuple[int,...]
  shift : int
  symbols_: dict[str,str] # inverse of symbols
  perm_: tuple[int,...] # inverse of perm
  shift_: int # complement of shift
  D: int
  bound: int
  slices: tuple[slice,...]

  def __init__(self,symbols:Optional[str]=None,perm:tuple[int,...]|int=4,shift:Optional[int]=None):
    from random import shuffle, getrandbits
    from string import ascii_letters, digits
    from math import log2
    P: int; D:int
    if symbols is None: s = list(digits+ascii_letters); shuffle(s); P=5; symbols = ''.join(s[:32])
    else: assert isinstance(symbols,str) and len(set(symbols)) == len(symbols); P = int(log2(len(symbols))); symbols = symbols[:(1<<P)]
    if isinstance(perm,int): D = perm*P; perml = list(range(D)); shuffle(perml); perm = tuple(perml)
    else: D = len(perm); assert D%P==0 and set(perm) == set(range(D))
    bound = (1<<D)-1
    if shift is None: shift = getrandbits(D)
    else: assert isinstance(shift,int) and shift>=0; shift &= bound
    self.D,self.shift,self.perm,self.bound,self.slices = D,shift,perm,bound,tuple(slice(i,i+P) for i in range(0,D,P))
    self.shift_ = bound-shift+1
    self.perm_ = tuple(perm.index(i) for i in range(D))
    fmt = f'0{P}b'; bits = [format(i,fmt) for i in range(len(symbols))]
    self.symbols = dict(zip(bits,symbols))
    self.symbols_ = dict(zip(symbols,bits))

#----------------------------------------------------------------------------------------------------------------------
  def int2str(self,n:int)->str:
    r""":param n: a whole number between :math:`0` and :math:`2^D-1` (not checked)"""
#----------------------------------------------------------------------------------------------------------------------
    #assert isinstance(n,int) and 0 <= n <= self.bound # check n: bounded-int
    n = (n+self.shift)&self.bound # shift: bounded-int -> bounded-int
    x = format(n,'b').rjust(self.D,'0') # convert: bounded-int -> bit-str
    x = ''.join(x[i] for i in self.perm) # permute: bit-str -> bit-str
    return ''.join(self.symbols[x[s]] for s in self.slices) # segment: bit-str -> symbol-str

#----------------------------------------------------------------------------------------------------------------------
  def str2int(self,x:str)->int:
    r""":param x: a string of symbols of length :math:`K` (not checked)"""
#----------------------------------------------------------------------------------------------------------------------
    #assert isinstance(x,str) and len(x)==len(self.slices) and all(u in self.symbols_ for u in x) # check x: symbol-str
    x = ''.join(self.symbols_[u] for u in x) # segment: symbol-str -> bit-str
    x = ''.join(x[i] for i in self.perm_) # permute: bit-str -> bit-str
    n = int(x,2) # convert: bit-str -> bounded-int
    return (n+self.shift_)&self.bound # shift: bounded-int -> bounded-int

#======================================================================================================================
class Backup:
  r"""
An instance of this class creates a context allowing transactional operations on the first level of a directory (called the root). A subdirectory of the root must be named, and will be used for backup. It should only be used for that purpose. The only allowed transactional operations take a single name (with no path separator) as input and move the file (or sub-directory) corresponding to that name from the root directory (if it exists) into the backup directory. If the context exits with an exception, all the files and directories affected by the transactional operations are restored, erasing new ones if needed. Example::

   with Backup('mydir') as backup:
     p1 = backup('file1') # file1 is moved (if it exists) to the backup directory; p1 is the Path object for the new file1
     p2 = backup('dir2')
     p1.write_text('Hello world')
     ...
     raise Exception() # file1 and dir2 are restored, possibly erasing the new content in p1,p2
  """
#======================================================================================================================
  def __init__(self,p:str|Path,name:str='.backup'):
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
@contextmanager
def http_request(method:str,url:str,**ka):
  r"""
A thin layer around :meth:`http.client.HTTPConnection.request`. Supports *url* in ``http``, ``https`` schemes and works as a python context yielding a :class:`http.client.HTTPResponse` object. The host specification in *url* can contain ``@`` to provide basic authentication (eventually removed from *url*) in the form of a login-password pair separated by ``:``  (if the password is omitted, it is read from the terminal), e.g. ``https://joe@example.com/some/path?some=query``.

With method GET, *url* can be a simple path to an existing file (*ka* must then be empty). The returned object supports only attributes :attr:`status`, :attr:`reason`, as well as method :meth:`read`, as in :class:`http.client.HTTPResponse` class.

:param method: HTTP method name (case ignored)
:param url: url to open
:param ka: same as in method :meth:`http.client.HTTPConnection.request`
  """
#======================================================================================================================
  from urllib.parse import urlparse, urlunparse
  from http.client import HTTPConnection, HTTPSConnection
  from functools import partial
  from getpass import getpass
  from base64 import b64encode
  class FileConnection:
    stream = path = status = reason = None
    def __init__(self,loc): assert not loc
    def request(self,method,path,**ka): assert method.upper()=='GET' and not ka; self.path = Path(path)
    def getresponse(self):
      import io, traceback
      try: self.stream = self.path.open('rb')
      except IOError as e: self.status = 500; self.reason = repr(e); self.read = io.BytesIO(traceback.format_exc().encode()).read
      else: self.status = 200; self.reason = 'OK'; self.read = self.stream.read
      return self
    def close(self):
      if self.stream is not None: self.stream.close()
  def auth(factory,loc):
    loc = loc.split('@',1)
    if len(loc)==1: return factory(loc[0])
    cred = loc[0].split(':',1)
    if len(cred)==1: cred = cred[0],getpass(f'Password for {cred[0]}@{loc[1]}> ')
    ka.setdefault('headers',{})['Authorization'] = f'Basic {b64encode(b":".join(x.encode() for x in cred)).decode()}'
    return factory(loc[1])
  p = urlparse(url)
  conn = {'http':partial(auth,HTTPConnection),'https':partial(auth,HTTPSConnection),'':FileConnection}[p.scheme](p.netloc)
  try:
    conn.request(method,urlunparse(('','')+p[2:]),**ka)
    resp = conn.getresponse()
    assert resp.status<300, (resp.status,resp.reason,resp.read().decode())
    yield resp
  finally: conn.close()

#======================================================================================================================
# Miscellaneous
#======================================================================================================================

class HTTPException (Exception):
  def __init__(self,status:HTTPStatus): self.status = status
def http_raise(status): raise HTTPException(status)
def http_ts(ts:float)->str: return datetime.fromtimestamp(ts,UTC).strftime('%a, %d %b %Y %H:%M:%S GMT')

def default_attach_namer(n:int,split=(lambda x: f'{x[:2]}/{x[-2:]}'))->str: return split(f'{n:04x}')

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
