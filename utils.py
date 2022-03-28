import sys,os,sqlite3,shutil,json,re,traceback,dill as pickle
from functools import cached_property, cache, singledispatch
from datetime import datetime
from pathlib import Path
from http import HTTPStatus
from urllib.parse import parse_qsl,urljoin
from typing import Union, Callable, Dict, Any
from enum import Enum

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

#======================================================================================================================
class IntStrConverter:
  r"""
An instance of this class is a 1-1 mapping between the interval of whole numbers from 0 (inclusive) to 0x100000 (exclusive) and a set of strings of the form \*\*/\*\* (each \* being a character in *symbols*). Suitable for defining attachment paths. Example::

   c = IntStrConverter(check=True) # all parameters are initialised randomly
   L = list(range(0x100000))
   assert [c.str2int(s) for s in [c.int2str(n) for n in L]] == L

:param shift: any integer
:param perm: a permutation of (0,...,19)
:param symbols: a string of length 32 where each character occurs only once
:param check: if :const:`True`, checks the value of each of the other parameters, and, when missing, generates some valid random value
  """
#======================================================================================================================
  shift : int
  perm : tuple[int,...]
  symbols : dict[str,str]
  perm_: tuple[int,...] # inverse of perm
  symbols_: dict[str,str] # inverse of symbols

  def __init__(self,shift:int=0xe1e06,perm:tuple[int,...]=(17,12,9,6,11,14,0,4,19,8,1,18,3,7,5,16,10,2,15,13),symbols:str='0123456789ABCDEFGHIJKLMNOPQRSTUV'):
    from random import randint, shuffle
    from string import ascii_uppercase, digits
    if shift is None: shift = randint(0,0x100000)
    else: assert isinstance(shift,int)
    if perm is None: p = list(range(20)); shuffle(p); perm = tuple(p)
    else: assert set(perm) == set(range(20))
    if symbols is None: s = list((digits+ascii_uppercase)[:32]); shuffle(s); symbols = ''.join(s)
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
    x = ''.join(self.symbols[x[i:i+5]] for i in range(0,20,5)) # segment: 20-bit-str -> 4-symbol-str
    return f'{x[:2]}/{x[-2:]}'

#----------------------------------------------------------------------------------------------------------------------
  def str2int(self,x:str)->int:
    r""":param x: value to convert"""
#----------------------------------------------------------------------------------------------------------------------
    #assert isinstance(x,str) and len(x)==5 and x[2] == '/' and all(u in self.symbols_ for t in (x[:2],x[-2:]) for u in t)
    x = ''.join(self.symbols_[u] for t in (x[:2],x[-2:]) for u in t) # segment: 4-symbol-str -> 20-bit-str
    x = ''.join(x[i] for i in self.perm_) # permute: 20-bit-str -> 20-bit-str
    n = int(x,2) # convert: 20-bit-str -> 20-bit-int
    return (n-self.shift)%0x100000 # shift: 20-bit-int -> 20-bit-int


#======================================================================================================================
# Utilities
#======================================================================================================================

class HTTPException (Exception):
  def __init__(self,status:HTTPStatus): self.status = status
def http_raise(status): raise HTTPException(status)
def http_ts(ts:float)->str: return datetime.utcfromtimestamp(ts).strftime('%a, %d %b %Y %H:%M:%S GMT')

#----------------------------------------------------------------------------------------------------------------------
def parse_input(mime:str='application/json',transf:bool=True):
#----------------------------------------------------------------------------------------------------------------------
  assert os.environ['CONTENT_TYPE'].startswith(mime)
  n = int(os.environ['CONTENT_LENGTH'])
  x = []
  while n>0:
    t = sys.stdin.buffer.read(n); m = len(t)
    if m==0: raise EOFError()
    x.append(t)
    n -= m
  r:Any = b''.join(x).decode() # default (utf-8) encoding used; should be parsed from parameters in CONTENT_TYPE header
  if transf:
    if mime == 'application/json': r = json.loads(r)
    elif mime == 'application/x-www-form-urlencoded': r = dict(parse_qsl(r)) # very basic, no multiple values with same field
  return r

#----------------------------------------------------------------------------------------------------------------------
class str_md(str): pass  # to identify Markdown strings
#----------------------------------------------------------------------------------------------------------------------
@singledispatch
def rebase(x,base): return urljoin(base,x)
@rebase.register(str_md)
def _(x,base,pat=re.compile(r'(\[.*?])\((.*?)( .*?)?\)')):
  return pat.sub((lambda m: f'{m.group(1)}({urljoin(base,m.group(2))}{m.group(3) or ""})'),x)
