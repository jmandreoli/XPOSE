# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: initialisation
#

import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from http.client import HTTPConnection, HTTPSConnection

#======================================================================================================================
def _initial(path,config,cgi_script,cgi_url):
  r"""
Pre-initialises an Xpose instance at *path*.
  """
#======================================================================================================================
  path = Path(path).resolve()
  assert path.is_dir() and not any(path.iterdir()), 'Target directory must be empty for xpose initialisation'
  config_ = path/'config.py'; config_.symlink_to(Path(config).resolve())
  init = f'''#!{sys.executable}
from os import environ, umask
from pathlib import Path
from xpose.server import XposeServer
umask(0o7)
XposeServer().setup('{path}').process_cgi()'''
  p = urlparse(cgi_url)
  conn = {'http':HTTPConnection,'https':HTTPSConnection}[p.scheme](p.netloc)
  cgi_script = Path(cgi_script)
  cgi_script.unlink(missing_ok=True)
  try:
    cgi_script.write_text(init);cgi_script.chmod(0o555)
    conn.request('POST',urlunparse(('','')+p[2:]))
    resp = conn.getresponse()
    print(resp.read().decode())
    assert resp.status == 200
  finally:
    cgi_script.unlink(missing_ok=True)
    conn.close()
  cgi_script.symlink_to(path/'route.py')
  return resp
