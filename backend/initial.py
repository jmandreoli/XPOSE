# Creation date:        2022-01-15
# Contributors:         Jean-Marc Andreoli
# Language:             python
# Purpose:              Xpose: initialisation
#

import sys, json, io, traceback
from pathlib import Path
from functools import partial

#======================================================================================================================
def _initial(_path:str,_config:str,_cgi_script:str,_cgi_url:str,_source:str):
  r"""
Xpose instance initialisation.

:param _path: a path to an existing directory where an Xpose instance is to be initialised, normally empty (except for re-initialisation)
:param _config: a path to an existing python file containing the configuration of the instance
:param _cgi_script: a path where the cgi script for the management of the instance will be created
:param _cgi_url: a url invoking *cgi_script*
:param _source:
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
  if _source is None: body = '{}'
  else:
    body = http_request('GET',_source).data
    body_ = json.loads(body)
    assert 'listing' in body_ and 'meta' in body_ and 'user_version' in body_['meta']
  try:
    cgi_script.write_text(init);cgi_script.chmod(0o555)
    print(http_request('PUT',_cgi_url,body=body,headers={'Content-Type':'application/json'}).data)
  finally:
    cgi_script.unlink(missing_ok=True)
  cgi_script.symlink_to(path/'route.py')

#----------------------------------------------------------------------------------------------------------------------
def http_request(method:str,url:str,**ka): # thin layer around http.client.HTTPConnection.request
#----------------------------------------------------------------------------------------------------------------------
  from urllib.parse import urlparse, urlunparse
  from http.client import HTTPConnection, HTTPSConnection
  from getpass import getpass
  from base64 import b64encode
  def auth(factory,loc):
    loc = loc.split('@',1)
    if len(loc)==1: return loc[0]
    cred = loc[0].split(':',1)
    if len(cred)==1: cred = cred[0],getpass(f'Password for {cred[0]@loc[1]}> ')
    ka.setdefault('headers',{})['Authorization'] = f'Basic {b64encode(b":".join(x.encode() for x in cred)).decode()}'
    return factory(loc[1])
  p = urlparse(url)
  conn = {'http':partial(auth,HTTPConnection),'https':partial(auth,HTTPSConnection),'':FileConnection}[p.scheme](p.netloc)
  try:
    conn.request(method,urlunparse(('','')+p[2:]),**ka)
    resp = conn.getresponse()
    resp.data = resp.read().decode()
    assert resp.status==200, (resp.status,resp.reason,resp.data)
  finally: conn.close()
  return resp

#----------------------------------------------------------------------------------------------------------------------
class FileConnection:
#----------------------------------------------------------------------------------------------------------------------
  stream = None
  def __init__(self,loc): assert not loc
  def request(self,method,path,**ka): assert method.upper()=='GET' and not ka; self.path = Path(path)
  def getresponse(self):
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
  parser.add_argument('path',metavar='PATH',help='Root directory of the Xpose instance to initialise')
  parser.add_argument('config',metavar='CONFIG',help='Python file giving the configuration of the Xpose instance to initialise')
  parser.add_argument('cgi_script',metavar='CGI-SCRIPT',help='Path to the cgi-script to invoke the Xpose instance (will be overridden)')
  parser.add_argument('cgi_url',metavar='CGI-URL',help='URL to invoke CGI-SCRIPT')
  parser.add_argument('source',metavar='SOURCE',nargs='?',help='file path or URL to a JSON formatted string suitable for Xpose load, loaded after initialisation',default=None)
  a = parser.parse_args(sys.argv[1:])
  _initial(a.path,a.config,a.cgi_script,a.cgi_url,a.source)
