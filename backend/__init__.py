# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: a JSON database manager (server side)
#

r"""
:mod:`XPOSE` (toplevel) --- base definitions
============================================
"""

import sqlite3,json
from functools import cached_property
from pathlib import Path
from typing import Optional, Union, Callable, Dict, Any
from .utils import get_config,set_config # not used, but made available
assert hasattr(Path,'hardlink_to'), 'You are using a version of python<3.10; try the fix below'
# Path.hardlink_to = lambda self,target: Path(target).link_to(self)
sqlite3.register_converter('JSON',json.loads)
sqlite3.register_adapter(dict,json.dumps)
sqlite3.enable_callback_tracebacks(True)

#======================================================================================================================
class XposeBase:
  r"""
An instances of this base class is a resource for processing Xpose operations. Actual behaviour is defined in subclasses.
  """
#======================================================================================================================

  root: Path
  r"""Path to the root folder"""
  index_db: Path
  r"""Path to the index database"""

  def setup(self,path:Union[str,Path]='.'):
    self.root = Path(path).resolve()
    self.index_db = self.root/'index.db'
    return self

#----------------------------------------------------------------------------------------------------------------------
  def connect(self,**ka):
    r"""
Returns a :class:`sqlite3.Connection` opened on the index database. The keyword arguments *ka* are passed as such to the connection constructor.
    """
#----------------------------------------------------------------------------------------------------------------------
    return sqlite3.connect(self.index_db,**ka)

#======================================================================================================================
class WithCatsMixin:
#======================================================================================================================
  root: Path
  @cached_property
  def cats(self)->'Cats': return Cats(self.root/'cats')

#======================================================================================================================
class Cats:
  r"""
An instance of this class manages all the xpose instance's categories (field ``cat`` in the index).
  """
#======================================================================================================================

  validators: dict[str,Any]

  def __init__(self,root:Path):
    self.root = root.resolve()
    self.validators = {}

#----------------------------------------------------------------------------------------------------------------------
  def initial(self,**ka):
    r"""
Initialises all the categories found (file ``init.py`` in any recursive sub-folder of ``cats``).
    """
#----------------------------------------------------------------------------------------------------------------------
    for pcat in self.root.glob('**/init.py'):
      exec(pcat.read_text(),{'cat':str(pcat.relative_to(self.root).parent),**ka})

#----------------------------------------------------------------------------------------------------------------------
  def validate(self,cat:str,value:object):
    r"""
Checks that *value*, viewed as a json object, conforms to the json schema associated with *cat*.

:param cat: the category against which to validate
:param value: the value to validate
    """
#----------------------------------------------------------------------------------------------------------------------
    validator = self.validators.get(cat)
    if validator is None:
      from jsonschema import Draft202012Validator,RefResolver
      base = self.root/cat/'schema.json'
      with base.open() as u: schema = json.load(u)
      Draft202012Validator.check_schema(schema)
      self.validators[cat] = validator = Draft202012Validator(schema=schema).evolve(resolver=RefResolver(f'file://{base}',{}))
    validator.validate(value)

  @cached_property
  def template_loader(self):
    from genshi.template import TemplateLoader
    return TemplateLoader(str(self.root),auto_reload=True)
  def load_template(self,tmpl):
    return self.template_loader.load(tmpl)
#----------------------------------------------------------------------------------------------------------------------
  def apply_template(self,tmpl:str,err_tmpl:str,rendering:Union[str,None],**args):
    r"""
Applies a template specified by *tmpl* with a set of variables specified by *args*. All templates are found in folder ``templates`` with relative path specifying the template role and category, and suffix ``.xhtml``.

:param tmpl: genshi template path (relative to the root)
:param err_tmpl: genshi template path, executed, with no variable, in case of error
    """
#----------------------------------------------------------------------------------------------------------------------
    try: return self.load_template(tmpl).generate(**args).render(rendering)
    except: return self.load_template(err_tmpl).generate().render(rendering)
