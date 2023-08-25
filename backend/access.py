# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: access control operations
#

import os,re
from functools import cached_property
from pathlib import Path
from lxml.etree import fromstring as xml
from typing import Optional, Callable, Dict, Any

#======================================================================================================================
class Credentials:
  r"""
An instance of this class extracts credentials recognised by Apache from the CGI context.
  """
#======================================================================================================================
  ldap_user_key = 'AUTHENTICATE_SAMACCOUNTNAME'
  ldap_group_key = 'AUTHENTICATE_MEMBEROF'
  user_key = 'REMOTE_USER'
  @cached_property
  def user(self)->Optional[str]: return os.environ.get(self.user_key)
  @cached_property
  def ldap_user(self)->Optional[str]: return os.environ.get(self.ldap_user_key)
  @cached_property
  def ldap_groups(self)->dict[str,bool]: return {} if (groups:=os.environ.get(self.ldap_group_key)) is None else dict((g,True) for g in groups.split('; '))

#======================================================================================================================
class Accessor:
  r"""
An instance of this class manages access to the xpose instances. This implementation is based on the apache authorisation framework.

:param directives: mapping each access level to an access control directive (must be acceptable in ``.htaccess`` files)
:param credentials: the credential object against which the directives are checked
  """
#======================================================================================================================

  _directive:dict[str,str]
  _check:dict[str,Callable[[Credentials],bool]]
  _checked: dict[str,bool]

  def __init__(self,directives:dict[str,str],credentials:Optional[Credentials]=None):
    def check_(directive):
      def check_base(directive,pat=re.compile(r'^Require\s+(\S+)(?:\s+(.*))?$')):
        if '\n' in directive: raise Exception('Single line clause expected')
        m = pat.match(directive)
        if m is not None: Exception('Require clause expected')
        match m.group(1):
          case 'user':
            L = m.group(2).split()
            return f'(credentials.user in ({",".join(map(repr,L))}))' if len(L)>1 else f'(credentials.user == {repr(L[0])})'
          case 'group': return f'(credentials.groups.get({repr(m.group(2))}) is not None)'
          case 'ldap-user':
            L = m.group(2).split()
            return f'(credentials.ldap_user in ({",".join(map(repr,L))}))' if len(L)>1 else f'(credentials.user == {repr(L[0])})'
          case 'ldap-group': return f'(credentials.ldap_groups.get({repr(m.group(2))}) is not None)'
          case _: Exception(f'Unsupported Require type: {m.group(1)}')
      def check_compound(d):
        def sub(d):
          t = d.text.strip()
          if t:
            for subdirective in t.split('\n'): yield check_base(subdirective.strip())
          for d_ in d:
            yield check_compound(d_)
            t = d_.tail.strip()
            if t:
              for subdirective in t.split('\n'): yield check_base(subdirective.strip())
        connector = {'RequireAny':' or ','RequireAll': ' and '}.get(d.tag)
        if connector is None: raise Exception(f'Unsupported clause connector: {d.tag}')
        return '({})'.format(connector.join(sub(d)))
      directive = directive.strip()
      try: return check_compound(xml(directive)) if directive.startswith('<') else check_base(directive)
      except: raise ValueError('Expected: Apache authorisation clause')
    self.credentials = credentials or Credentials()
    self._directive = directives
    self._check = {}
    self._checked = {}
    for level,directive in directives.items():
      body = check_(directive)
      checker = eval(f'lambda credentials: {body}',{'self':self})
      checker.__doc__ = body
      self._check[level] = checker

  def authorise(self,level:str)->bool:
    r"""
Checks whether access to an entity is authorised at *level*.
    """
    if level is None: return True
    r = self._checked.get(level)
    if r is None: r = self._checked[level] = self._check[level](self.credentials)
    return r

  def authoriser(self,level:str,path:Path):
    r"""
Restricts access to *path* at *level*.
    """
    p = path/'.htaccess'
    if level is not None: p.parent.mkdir(parents=True,exist_ok=True);p.write_text(self._directive[level])
    elif p.exists(): p.unlink()
