# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: attachment operations
#

import shutil
from functools import cached_property
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Dict, Any

#======================================================================================================================
class Attach:
  r"""
An instance of this class manages an xpose instance's attachments (field ``attach`` in the index).
  """
#======================================================================================================================

  def __init__(self,root): self.root = root.resolve()

#----------------------------------------------------------------------------------------------------------------------
  def getpath(self,path:str|Path)->tuple[Path,int]:
    r"""Returns the absolute path of *path*, and its depth level."""
#----------------------------------------------------------------------------------------------------------------------
    path_ = (self.root/path).resolve()
    level = len(path_.relative_to(self.root).parts)-2
    assert level>=0
    return path_,level

#----------------------------------------------------------------------------------------------------------------------
  def ls(self,path:Path)->list[tuple[str,str,int]]:
    r"""Returns the list of contents of *path*."""
#----------------------------------------------------------------------------------------------------------------------
    def E(p:Path)->tuple[bool,str,str,int]:
      s = p.stat(); return p.is_dir(),p.name,datetime.fromtimestamp(s.st_mtime).isoformat(timespec='seconds'),(s.st_size if p.is_file() else -len(list(p.iterdir())))
    if not path.is_dir(): return []
    if (content:=sorted(map(E,path.iterdir()))): return [x[1:] for x in content]
    while True: # recursively remove all empty ancestors (up to root)
      try: path.rmdir()
      except: break
      else:
        path = path.parent
        if path==self.root: break
    return []

#----------------------------------------------------------------------------------------------------------------------
  def perform(self,path:Path,src,trg,is_new:bool):
    r"""
Executes an operation on *path*. Essentially renames *src* to *trg* (or removes the former if the latter is empty).

:param src: source path of the op
:param trg: target path of the op (possibly empty)
:param is_new: whether the source should be found in ``.uploaded`` directory
    """
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
  def rmdir(self,path:Path,check_exists=True):
    r"""Removes a directory *path*, after checking it exists if *check_exists* is true."""
#----------------------------------------------------------------------------------------------------------------------
    if check_exists and not (self.root/path).exists(): return
    shutil.rmtree(self.root/path)

#----------------------------------------------------------------------------------------------------------------------
  def upload(self,it)->tuple[str,str,int]:
    r"""Uploads a stream of byte strings *it* to directory ``.uploaded``. Returns a triple of the name of the uploaded file, its last modification time, and its current size (in bytes)"""
#----------------------------------------------------------------------------------------------------------------------
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile('wb',dir=self.root/'.uploaded',prefix='',delete=False) as v:
      f = Path(v.name)
      try:
        for x in it: v.write(x)
      except: f.unlink(); raise
    s = f.stat()
    return f.name,datetime.fromtimestamp(s.st_mtime).isoformat(timespec='seconds'),s.st_size

#======================================================================================================================
class WithAttachMixin:
#======================================================================================================================
  root:Path
  @cached_property
  def attach(self)->Attach: return Attach(self.root/'attach')
