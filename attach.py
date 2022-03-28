# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: a JSON database manager (server side)
#

import sys,os,json,shutil
from pathlib import Path
from datetime import datetime
from http import HTTPStatus
from urllib.parse import parse_qsl
from typing import Union, Callable, Dict, Any
from . import XposeBase
from utils import CGIMixin,http_raise,http_ts,parse_input

#======================================================================================================================
class XposeAttach (XposeBase,CGIMixin):
  r"""
An instance of this class is a CGI resource managing the Xpose attachment folder.
  """
#======================================================================================================================

  def __init__(self,umask:int=0o2,chunk:int=0x100000,**ka):
    os.umask(umask)
    self.chunk = chunk
    super().__init__(**ka)

#----------------------------------------------------------------------------------------------------------------------
  def do_get(self):
    r"""
Input is expected as an (encoded) form with a single field ``path``.
    """
#----------------------------------------------------------------------------------------------------------------------
    form = dict(parse_qsl(os.environ['QUERY_STRING']))
    path,level = self.attach.getpath(form['path'])
    content = self.attach.ls(path)
    return json.dumps({'content':content,'version':self.version(path),'toplevel':level==0}),{'Content-Type':'text/json'}

#----------------------------------------------------------------------------------------------------------------------
  def do_patch(self):
    r"""
Input is expected as a JSON encoded object with fields ``path``, ``version`` and ``ops``, the latter being a list of operations. An operation is specified as an object with fields ``src``, ``trg`` (relative paths) and ``is_new`` (boolean).
    """
#----------------------------------------------------------------------------------------------------------------------
    content = parse_input()
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
    form = dict(parse_qsl(os.environ['QUERY_STRING']))
    target = form.get('target')
    assert os.environ['CONTENT_TYPE'] == 'application/octet-stream'
    res = self.attach.upload(sys.stdin.buffer,int(os.environ['CONTENT_LENGTH']),target,chunk=self.chunk)
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

#======================================================================================================================
class Attach:
  r"""
An instance of this class manages an xpose instance's attachments (field ``attach`` in the index).
  """
#======================================================================================================================

  def __init__(self,root,namer): self.root,self.namer = root,namer

#----------------------------------------------------------------------------------------------------------------------
  def getpath(self,path:Union[str,Path]):
#----------------------------------------------------------------------------------------------------------------------
    path_ = (self.root/path).resolve()
    level = len(path_.relative_to(self.root).parts)-2
    assert level>=0
    return path_,level

#----------------------------------------------------------------------------------------------------------------------
  def ls(self,path:Path):
#----------------------------------------------------------------------------------------------------------------------
    def E(p): s = p.stat(); return p.is_dir(),p.name,datetime.fromtimestamp(s.st_mtime).isoformat(timespec='seconds'),(s.st_size if p.is_file() else -len(list(p.iterdir())))
    if not path.is_dir(): return []
    content = L = sorted(map(E,path.iterdir()))
    while not L:
      path.rmdir()
      path = path.parent
      if path==self.root: break
      L = list(path.iterdir())
    return [x[1:] for x in content]

#----------------------------------------------------------------------------------------------------------------------
  def do(self,path:Path,src,trg,is_new:bool):
#----------------------------------------------------------------------------------------------------------------------
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

#----------------------------------------------------------------------------------------------------------------------
  def rmdir(self,path:Path,check_exists=False):
#----------------------------------------------------------------------------------------------------------------------
    if check_exists and not (self.root/path).exists(): return
    shutil.rmtree(self.root/path)

#----------------------------------------------------------------------------------------------------------------------
  def upload(self,buf,size:int,target,chunk:int):
#----------------------------------------------------------------------------------------------------------------------
    from tempfile import NamedTemporaryFile
    upload_dir = self.root/'.uploaded'
    if size==0: (upload_dir/target).unlink(); return
    with ((upload_dir/target).open('ab') if target else NamedTemporaryFile('wb',dir=upload_dir,prefix='',delete=False)) as v:
      f = Path(v.name)
      try:
        while size>0:
          t = buf.read(min(size,chunk))
          n = len(t)
          if n==0: raise EOFError()
          v.write(t)
          size -= n
      except: f.unlink(); raise
    s = f.stat()
    return f.name,datetime.fromtimestamp(s.st_mtime).isoformat(timespec='seconds'),s.st_size
