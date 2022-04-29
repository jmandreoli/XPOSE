# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: initialisation
#

r"""
:mod:`XPOSE.initial` --- initialisation
=======================================

To initialise an Xpose instance, run the command::

   PYTHONPATH=<path-to-xpose-package> <python-exe> -m xpose.initial <arguments>

where

* the ``PYTHONPATH`` enviroment variable must give access to the XPOSE package
* the resulting cgi-script will use the same python executable as specified in the command
* the meaning of the arguments can be obtained by passing option ``-h`` or ``--help``

The command above assumes the name of the XPOSE package is xpose (default). It may be changed, in which case it must be changed in the ``-m`` option above, and must also be explicitly provided with option ``-x``.
"""


import sys, json
from pathlib import Path
from importlib import import_module

#======================================================================================================================
def run(_path:str,_cgi_script:str,_cgi_url:str,_config:str='./config.py',_load:str=None,_pname:str='xpose'):
  r"""
Xpose instance initialisation.

:param _path: a path to an existing directory where an Xpose instance is to be initialised, normally empty (except for re-initialisation)
:param _cgi_script: a path where the cgi script for the management of the instance will be created
:param _cgi_url: a url invoking *_cgi_script*
:param _config: a path to an existing python file containing the configuration of the instance
:param _load: a url from which to retrieve an initial dump of entries, loaded into the instance (if not :const:`None`)
:param _pname: the name of the XPOSE package
  """
#======================================================================================================================
  path = Path(_path).resolve()
  assert path.is_dir()
  http_request = import_module(f'{_pname}.utils').http_request
  init = f'''#!{Path(sys.executable).resolve()}
from os import environ, umask
from pathlib import Path
from {_pname}.server import XposeServer
umask(0o7)
XposeServer().setup('{path}').process_cgi()'''
  config = path/'config.py'
  config.unlink(missing_ok=True)
  config.symlink_to(Path(_config).resolve())
  cgi_script = Path(_cgi_script)
  cgi_script.unlink(missing_ok=True)
  if _load is None: body = 'null'
  else:
    with http_request('GET',_load) as resp: body = resp.read().decode()
  try:
    cgi_script.write_text(init);cgi_script.chmod(0o555)
    with http_request('PUT',_cgi_url,body=body,headers={'Content-Type':'application/json'}) as resp:
      R = resp.read().decode()
  finally:
    cgi_script.unlink(missing_ok=True)
  cgi_script.symlink_to(path/'route.py')
  return R

#----------------------------------------------------------------------------------------------------------------------
if __name__=='__main__':
#----------------------------------------------------------------------------------------------------------------------
  import argparse
  parser = argparse.ArgumentParser(
    description='Initialises an Xpose instance.',
    epilog='Observe that the content of the LOAD file or url must specify attachments as existing absolute paths on the local machine (where the initialisation is executed and where the server will be running). If LOAD is a dump from another Xpose instance running on a different (remote) machine with a different file system, the following two steps must be performed: 1- the attachments of the remote Xpose must be rsynced onto the local machine; 2- if the absolute paths cannot be preserved (e.g. a prefix must be changed, or the two file systems are not of the same type, like posix), the dump must be saved in a file and each attachment path in it must be adapted. The initialisation can then be run with LOAD pointing to that adapted dump file.'
  )
  parser.add_argument('-x','--xpose',dest='pname',metavar='PNAME',help='The package name of XPOSE in the server package lib (default: "xpose")',required=False,default='xpose')
  parser.add_argument('-l','--load',help='file path or URL to a JSON formatted content suitable for Xpose load, loaded after initialisation (default: none)',required=False,default=None)
  parser.add_argument('-c','--config',help='Python file giving the configuration of the Xpose instance to initialise (default: "./config.py")',required=False,default='./config.py')
  parser.add_argument('path',metavar='PATH',help='Root directory of the Xpose instance to initialise (OVERRIDDEN)')
  parser.add_argument('cgi_script',metavar='CGI-SCRIPT',help='Path to the cgi-script to invoke the Xpose instance (OVERRIDDEN)')
  parser.add_argument('cgi_url',metavar='CGI-URL',help='URL to invoke CGI-SCRIPT')
  a = parser.parse_args(sys.argv[1:])
  R = run(_path=a.path,_cgi_script=a.cgi_script,_cgi_url=a.cgi_url,_config=a.config,_load=a.load,_pname=a.pname)
  print(f'''Initialisation successful. You should now create a file xpose.html in the server 
''')