import sys
from argparse import ArgumentParser
from xpose import XposeServer

parser = ArgumentParser(description='Xpose Admin operation')
parser.add_argument('--with_oid',action='store_true',help='include oids')
parser.add_argument('--where',help='specifies what to dump (dump op only)')
parser.add_argument('op',choices=['load','dump'])
parser.add_argument('path',metavar='PATH')
args = parser.parse_args(sys.argv[1:])

xpose=XposeServer()
ka = {}
if args.where is not None: ka.update(where=args.where)
#def noop(*a,**ka): print(a,ka)
#noop(args.path,with_oid=args.with_oid,**ka)
getattr(xpose,args.op)(args.path,with_oid=args.with_oid,**ka)

