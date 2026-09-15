import os,sys
from pathlib import Path
ROOT=Path('/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/DELIVERY_OBSERVER_VERIFY').resolve()
blocked=[]
def audit(event,args):
    if event.startswith(('socket.bind','socket.connect','socket.getaddrinfo','socket.gethostby','socket.sendto','os.system','os.posix_spawn','os.exec')) or event=='sqlite3.connect':
        blocked.append(event); raise PermissionError('Diagnostic denies network/database/escape: '+event)
    if event=='subprocess.Popen' and Path(os.fsdecode(args[0])).resolve()!=Path(sys.executable).resolve():
        raise PermissionError('Only native local Python worker allowed')
    paths=[]
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        p,mode,flags=args
        if Path(os.fsdecode(p)).name.startswith('.env'): raise PermissionError('Secret reads forbidden')
        if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):paths=[p]
    elif event in ('os.mkdir','os.remove','os.rmdir','os.chmod','os.utime'):paths=[args[0]]
    elif event in ('os.rename','os.link','os.symlink'):paths=[args[0],args[1]]
    for p in paths:
        if isinstance(p,(str,bytes,os.PathLike)) and Path(os.fsdecode(p)).resolve()!=Path('/dev/null') and not Path(os.fsdecode(p)).resolve().is_relative_to(ROOT): raise PermissionError('Diagnostic write outside owned root')
sys.addaudithook(audit)
GUARD=True
