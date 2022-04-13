# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: attachment folder operations
#

import shutil
from functools import cached_property
from pathlib import Path
from datetime import datetime
from typing import Union, Callable, Dict, Any

#======================================================================================================================
class Attach:
  r"""
An instance of this class manages an xpose instance's attachments (field ``attach`` in the index).
  """
#======================================================================================================================

  def __init__(self,root): self.root = root.resolve()

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
  def upload(self,it,target):
#----------------------------------------------------------------------------------------------------------------------
    from tempfile import NamedTemporaryFile
    upload_dir = self.root/'.uploaded'
    if it is None: (upload_dir/target).unlink(); return
    with ((upload_dir/target).open('ab') if target else NamedTemporaryFile('wb',dir=upload_dir,prefix='',delete=False)) as v:
      f = Path(v.name)
      try:
        for x in it: v.write(x)
      except: f.unlink(); raise
    s = f.stat()
    return f.name,datetime.fromtimestamp(s.st_mtime).isoformat(timespec='seconds'),s.st_size

#----------------------------------------------------------------------------------------------------------------------
  def upload1(self,buf,size:int,target,chunk:int):
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

#======================================================================================================================
class WithAttachMixin:
#======================================================================================================================
  root:Path
  @cached_property
  def attach(self)->Attach: return Attach(self.root/'attach')
