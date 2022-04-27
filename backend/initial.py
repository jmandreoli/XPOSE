# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: initialisation
#

r"""
:mod:`XPOSE.initial` --- initialisation
=======================================

This file can be directly executed as::

   PYTHONPATH=<path-to-xpose-package> <python-exe> -m xpose.initial <arguments>

where

* the ``PYTHONPATH`` enviroment variable must give access to the XPOSE package (the name, here 'xpose', may be different)
* the python executable must be the same as the one used by the cgi-script to install
* the meaning of the arguments can be obtained by passing option ``-h`` or ``--help``
"""


import sys, json
from pathlib import Path
from contextlib import contextmanager

#======================================================================================================================
def initial(_path:str,_config:str,_cgi_script:str,_cgi_url:str,_source:str=None,_pname:str='xpose'):
  r"""
Xpose instance initialisation.

:param _path: a path to an existing directory where an Xpose instance is to be initialised, normally empty (except for re-initialisation)
:param _config: a path to an existing python file containing the configuration of the instance
:param _cgi_script: a path where the cgi script for the management of the instance will be created
:param _cgi_url: a url invoking *_cgi_script*
:param _source: a url from which to retrieve an initial dump of entries (if not :const:`None`)
:param _pname: the name of the XPOSE package as available from *_cgi_script*
  """
#======================================================================================================================
  path = Path(_path).resolve()
  assert path.is_dir()
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
  if _source is None: body = '{}'
  else:
    with http_request('GET',_source) as resp: body = resp.read().decode()
    body_ = json.loads(body)
    assert 'listing' in body_ and 'meta' in body_ and 'user_version' in body_['meta']
  try:
    cgi_script.write_text(init);cgi_script.chmod(0o555)
    with http_request('PUT',_cgi_url,body=body,headers={'Content-Type':'application/json'}) as resp:
      print(resp.read().decode())
  finally:
    cgi_script.unlink(missing_ok=True)
  cgi_script.symlink_to(path/'route.py')

#----------------------------------------------------------------------------------------------------------------------
@contextmanager
def http_request(method:str,url:str,**ka):
  r"""
A thin layer around :meth:`http.client.HTTPConnection.request`. Supports *url* in ``http``, ``https`` schemes as well as direct file path names. Works as a python context yielding a response object similar to :class:`http.client.HTTPResponse`. With http(s) scheme, the host can contain ``@`` to provide basic authentication in the form of a login-password pair separated by ``:``  (if the password is ommitted, it is read from the terminal), e.g. ``https://joe@example.com/some/path?some=query``.

:param method: HTTP method name (case ignored)
:param url: url to open
:param ka: same as for :meth:`http.client.HTTPConnection.request`
  """
#----------------------------------------------------------------------------------------------------------------------
  from urllib.parse import urlparse, urlunparse
  from http.client import HTTPConnection, HTTPSConnection
  from functools import partial
  from getpass import getpass
  from base64 import b64encode
  def auth(factory,loc):
    loc = loc.split('@',1)
    if len(loc)==1: return factory(loc[0])
    cred = loc[0].split(':',1)
    if len(cred)==1: cred = cred[0],getpass(f'Password for {cred[0]}@{loc[1]}> ')
    ka.setdefault('headers',{})['Authorization'] = f'Basic {b64encode(b":".join(x.encode() for x in cred)).decode()}'
    return factory(loc[1])
  p = urlparse(url)
  conn = {'http':partial(auth,HTTPConnection),'https':partial(auth,HTTPSConnection),'':FileConnection}[p.scheme](p.netloc)
  try:
    conn.request(method,urlunparse(('','')+p[2:]),**ka)
    resp = conn.getresponse()
    assert resp.status<300, (resp.status,resp.reason,resp.read().decode())
    yield resp
  finally: conn.close()

#----------------------------------------------------------------------------------------------------------------------
class FileConnection:
#----------------------------------------------------------------------------------------------------------------------
  stream = None
  def __init__(self,loc): assert not loc
  def request(self,method,path,**ka): assert method.upper()=='GET' and not ka; self.path = Path(path)
  def getresponse(self):
    import io, traceback
    try: self.stream = self.path.open('rb')
    except IOError as e: self.status = 500; self.reason = repr(e); self.read = io.BytesIO(traceback.format_exc().encode()).read
    else: self.status = 200; self.reason = 'OK'; self.read = self.stream.read
    return self
  def close(self):
    if self.stream is not None: self.stream.close()

#----------------------------------------------------------------------------------------------------------------------
if __name__=='__main__':
#----------------------------------------------------------------------------------------------------------------------
  import argparse
  parser = argparse.ArgumentParser(description='Initialises an Xpose instance.')
  parser.add_argument('-x','--xpose',target='pname',metavar='PNAME',help='The package name of XPOSE in the server package lib (default "xpose")',required=False,default='xpose')
  parser.add_argument('path',metavar='PATH',help='Root directory of the Xpose instance to initialise')
  parser.add_argument('config',metavar='CONFIG',help='Python file giving the configuration of the Xpose instance to initialise')
  parser.add_argument('cgi_script',metavar='CGI-SCRIPT',help='Path to the cgi-script to invoke the Xpose instance (will be overridden)')
  parser.add_argument('cgi_url',metavar='CGI-URL',help='URL to invoke CGI-SCRIPT')
  parser.add_argument('source',metavar='SOURCE',nargs='?',help='file path or URL to a JSON formatted string suitable for Xpose load, loaded after initialisation',default=None)
  a = parser.parse_args(sys.argv[1:])
  initial(a.path,a.config,a.cgi_script,a.cgi_url,a.source,a.pname)
