import os,sys
from pathlib import Path
ROOT=Path('/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/RUNTIME02_PUBLICATION_VERIFY').resolve()
blocked=[]
fd_paths = {}
pending_open = []
original_open, original_close = os.open, os.close
def resolve_path(value, dir_fd=None):
    if isinstance(value, int):
        if value not in fd_paths: raise PermissionError('Unknown file descriptor')
        return fd_paths[value]
    path=Path(os.fsdecode(value))
    if not path.is_absolute() and dir_fd not in (None, -1):
        if dir_fd not in fd_paths: raise PermissionError('Unknown directory descriptor')
        path=fd_paths[dir_fd]/path
    return path.resolve()
def tracked_open(path, flags, mode=0o777, *, dir_fd=None):
    resolved=resolve_path(path, dir_fd)
    pending_open.append(resolved)
    try:
        fd=original_open(path, flags, mode, dir_fd=dir_fd)
        fd_paths[fd]=resolved
        return fd
    finally: pending_open.pop()
def tracked_close(fd):
    try: return original_close(fd)
    finally: fd_paths.pop(fd, None)
os.open, os.close=tracked_open, tracked_close
def audit(event,args):
    if event.startswith(('socket.bind','socket.connect','socket.getaddrinfo','socket.gethostby','socket.sendto','os.system','os.posix_spawn','os.exec')) or event=='sqlite3.connect':
        blocked.append(event); raise PermissionError('Diagnostic denies network/database/escape: '+event)
    if event=='subprocess.Popen' and Path(os.fsdecode(args[0])).resolve()!=Path(sys.executable).resolve():
        raise PermissionError('Only native local Python worker allowed')
    paths=[]
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        p,mode,flags=args
        if Path(os.fsdecode(p)).name.startswith('.env'): raise PermissionError('Secret reads forbidden')
        if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):paths=[pending_open[-1] if pending_open else p]
    elif event in ('os.mkdir','os.remove','os.rmdir','os.chmod','os.utime'):paths=[resolve_path(args[0], args[-1] if isinstance(args[-1],int) else None)]
    elif event in ('os.rename','os.link'):paths=[resolve_path(args[0],args[2]),resolve_path(args[1],args[3])]
    elif event=='os.symlink':paths=[resolve_path(args[1],args[2])]
    for p in paths:
        if isinstance(p,(str,bytes,os.PathLike)) and Path(os.fsdecode(p)).resolve()!=Path('/dev/null') and not Path(os.fsdecode(p)).resolve().is_relative_to(ROOT): raise PermissionError('Diagnostic write outside owned root')
sys.addaudithook(audit)
GUARD=True
