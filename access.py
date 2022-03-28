import os
from functools import cached_property, cache
from pathlib import Path
from typing import Union, Callable, Dict, Any

#======================================================================================================================
class Accessor:
  r"""
An instance of this class manages access to the xpose instances. This implementation is based on the apache authorisation framework. Methods :meth:`directive` and :meth:`check` depend on the authorisation provider type, and must be defined in subclasses.
  """
#======================================================================================================================

  def authorise(self,level:str)->bool:
    r"""
Checks whether access to an entity is authorised at *level*.
    """
    return level is None or self.check(level)

  def authorise_folder(self,level:str,path:Path):
    r"""
Restricts access to *path* at *level*.
    """
    p = path/'.htaccess'
    if level is not None: p.parent.mkdir(parents=True, exist_ok=True);p.write_text(self.directive(level))
    elif p.exists(): p.unlink()

  def directive(self,level:str)->str:
    # Returns the apache directive needed to restrict access to a folder at *level*.
    raise NotImplementedError()

  def check(self,level:str)->bool:
    # Computes access authorisation at *level*. Should be equivalent to the apache directive.
    raise NotImplementedError()

#======================================================================================================================
class FileAccessor (Accessor):
  r"""
An instance of this class manages access to the xpose instances using the default file-based authorisation provider type (user restrictions only, group not supported).
  """
#======================================================================================================================
  def __init__(self,**ka): self._levels = dict((level,tuple(users)) for level,users in ka.items())
  @cached_property
  def credentials(self): return os.environ.get('REMOTE_USER')
  @cache
  def check(self,level:str)->bool: return self.credentials in self._levels[level]
  def directive(self,level:str)->str: return f'Require user {" ".join(self._levels[level])}'

#======================================================================================================================
class LdapAccessor (Accessor):
  r"""
An instance of this class manages access to the xpose instances using the ldap-based authorisation provider type (user and group restrictions both supported).
  """
#======================================================================================================================
  _check: dict[str,Callable[[],bool]]
  _directive: dict[str,str]
  def __init__(self,_ldap_keys=('AUTHENTICATE_SAMACCOUNTNAME','AUTHENTICATE_MEMBEROF'),**ka):
    self.ldap_keys = _ldap_keys
    self._check = {}; self._directive = {}
    for level,(users,groups) in ka.items():
      checks,directives = [],[]
      if users:
        checks.append(lambda: self.credentials[0] in users)
        directives.append(f'Require ldap-user {" ".join(users)}')
      if groups:
        groups_ = dict((g,True) for g in groups)
        checks.append(lambda: any(groups_.get(g) is not None for g in self.credentials[1]))
        directives.extend(f'Require ldap-group "{g}"' for g in groups)
      directives_ = '\n'.join(directives)
      self._check[level] = (lambda checks=tuple(checks):any(c() for c in checks)) if len(checks)>1 else checks[0]
      self._directive[level] = f'<RequireAny>\n{directives_}\n</RequireAny>' if len(directives)>1 else directives[0]
  @cached_property
  def credentials(self):
    user_key,group_key = self.ldap_keys
    return os.environ.get(user_key),(() if (groups:=os.environ.get(group_key)) is None else groups.split('; '))
  @cache
  def check(self,level:str)->bool: return self._check[level]()
  def directive(self,level:str)->str: return self._directive[level]
