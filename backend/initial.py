# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: initialisation
#

import sys
from pathlib import Path

#======================================================================================================================
def _initial(_path:str,_config:str,_cgi_script:str,_cgi_url:str,headers={}):
  r"""
Xpose instance initialisation.

:param _path: a path to an existing directory where an Xpose instance is to be initialised, normally empty (except for re-initialisation)
:param _config: a path to an existing python file containing the configuration of the instance
:param _cgi_script: a path where the cgi script for the management of the instance will be created
:param _cgi_url: a url invoking *cgi_script*
  """
#======================================================================================================================
  path = Path(_path).resolve()
  assert path.is_dir()
  init = f'''#!{Path(sys.executable).resolve()}
from os import environ, umask
from pathlib import Path
from xpose.server import XposeServer
umask(0o7)
XposeServer().setup('{path}').process_cgi()'''
  config = path/'config.py'
  config.unlink(missing_ok=True)
  config.symlink_to(Path(_config).resolve())
  cgi_script = Path(_cgi_script)
  cgi_script.unlink(missing_ok=True)
  try:
    cgi_script.write_text(init);cgi_script.chmod(0o555)
    resp = http_request('POST',_cgi_url,headers=headers)
    print(resp.data.decode())
    assert resp.status == 200
  finally:
    cgi_script.unlink(missing_ok=True)
  cgi_script.symlink_to(path/'route.py')

#----------------------------------------------------------------------------------------------------------------------
def http_request(method:str,url:str,**ka): # thin layer around http.client.HTTPConnection.request
#----------------------------------------------------------------------------------------------------------------------
  from urllib.parse import urlparse, urlunparse
  from http.client import HTTPConnection, HTTPSConnection
  p = urlparse(url)
  conn = {'http':HTTPConnection,'https':HTTPSConnection}[p.scheme](p.netloc)
  try:
    conn.request(method,urlunparse(('','')+p[2:]),**ka)
    resp = conn.getresponse()
    resp.data = resp.read()
  finally: conn.close()
  return resp

if __name__=='__main__': _initial(*sys.argv[1:])
