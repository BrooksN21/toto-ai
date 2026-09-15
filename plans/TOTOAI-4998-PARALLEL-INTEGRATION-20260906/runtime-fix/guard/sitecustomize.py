import os,sys
from pathlib import Path
ROOT=Path('/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/runtime-fix').resolve()
def allowed(p):
    if isinstance(p,int): return True
    return Path(p).absolute().is_relative_to(ROOT)
def audit(event,args):
    if event in ('socket.connect','socket.getaddrinfo','sqlite3.connect'):
        raise RuntimeError('offline replay: network/DB forbidden')
    if event=='open':
        p,mode,flags=args
        if isinstance(p,str) and p.endswith(('.db','.sqlite','.sqlite3')): raise RuntimeError('offline replay: DB access forbidden')
        writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC))
        if writing and not allowed(p): raise RuntimeError('offline replay: protected write forbidden')
    if event in ('os.rename','os.remove','os.rmdir','os.mkdir'):
        targets=args[:2] if event=='os.rename' else args[:1]
        if not all(allowed(p) for p in targets): raise RuntimeError('offline replay: protected mutation forbidden')
    if event=='subprocess.Popen':
        argv=args[1]
        if argv != [sys.executable,'-B','-m','toto_ai.sports_stats.parallel_g1']:
            raise RuntimeError('offline replay: only existing local G1 child permitted')
sys.addaudithook(audit)
