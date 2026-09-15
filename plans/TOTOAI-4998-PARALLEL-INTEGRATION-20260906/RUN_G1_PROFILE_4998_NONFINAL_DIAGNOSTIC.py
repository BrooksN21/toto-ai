"""One bounded offline research diagnostic; not a scheduler or operator run."""
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path

from toto_ai.runner.final_input import load_final_input
from toto_ai.runner.scheduler import load_scheduler_plan
from toto_ai.sports_stats import final_hybrid_comparison as comparison
from toto_ai.sports_stats.probabilities import load_shadow_probability_artifact

M = Path('/Users/turshevr/toto-ai')
D = M / 'plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906'
plan_path = M / 'reports/rehearsal/evening-4998-20260906T153000Z/scheduler-plan.json'
seed = plan_path.parent / 'parallel-challenger/sports-seed/sports_probability_shadow_4998_ac04ea9b30359094.json'
plan = load_scheduler_plan(plan_path)
assert (plan.plan_id, plan.drawing, plan.drawing_id, plan.requested_bank, plan.stake) == ('c1d243f5b6ca48f3', 4998, 12102, 4980, 30)
now = datetime.now(timezone.utc)
assert now < datetime(2026, 9, 6, 14, 20, tzinfo=timezone.utc), 'Too late for8min diagnostic before17:28'
prior_path = D/'4998_NONFINAL_DIAGNOSTIC_RECEIPT.json'
prior = json.loads(prior_path.read_text())
prior_receipt_hash = hashlib.sha256(prior_path.read_bytes()).hexdigest()
original_input = Path(prior['input_path'])
assert hashlib.sha256(original_input.read_bytes()).hexdigest() == prior['snapshot_file_sha256'] == '55dd85d18e592ae4aefaa0acfc2b4ab8bb4fcd9d99b73df95e8a87124702b330'
raw = SimpleNamespace(path=Path(prior['source_cache']), fetched_at=datetime.fromisoformat(prior['source_fetched_at']), payload_sha256=prior['source_payload_sha256'])
sports = load_shadow_probability_artifact(seed)
assert hashlib.sha256(seed.read_bytes()).hexdigest() == '2d5003c79378fb0b5f425ddf8cfdc0902327e727c0c0f3bb43843b43f2139e78'
assert sports.as_of <= raw.fetched_at <= now
stamp = now.strftime('%Y%m%dT%H%M%S%fZ')
out = M / 'reports/research/4998' / ('G1-PROFILE-NONFINAL-RESEARCH-DIAGNOSTIC-' + stamp)
out.mkdir(parents=True, exist_ok=False)
(out/'input').mkdir()
(out/'bootstrap').mkdir()
(out/'tmp').mkdir()
(out/'README.md').write_text('NONFINAL PRE-DRAW RESEARCH DIAGNOSTIC ONLY — NOT OPERATOR, NOT FINAL, NOT FOR WAGERING OR UPLOAD.\nNative research coupon files remain explicitly non-BaltBet. No delivery.\n')
# Typed envelope is native to existing morning-training path; actual cache time is retained.
copied_input = out/'input/NONFINAL-plan-bound-input.json'
copied_input.write_bytes(original_input.read_bytes())
snapshot = load_final_input(copied_input, expected_plan=plan)
assert snapshot.snapshot_sha256 == prior['snapshot_sha256']
assert hashlib.sha256(copied_input.read_bytes()).hexdigest() == prior['snapshot_file_sha256']
frozen = comparison.frozen_input_from_snapshot(snapshot, plan)
comparison._validate_sports_artifact_identity(plan=plan, snapshot=snapshot, frozen=frozen, sports=sports)
protected_paths = [plan_path, seed, plan_path.parent/'run-scheduler.sh', plan_path.parent/'experimental-manual-release-authorization.json', plan_path.parent/'parallel-challenger/parallel-release-authorization.json', plan_path.parent/'parallel-challenger/run-parallel-sidecar.sh', plan_path.parent/'totoai-scheduler.plist', plan_path.parent/'parallel-challenger/totoai-parallel-sidecar.plist']
H = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
protected = {str(p): H(p) for p in protected_paths}
source_files = ['src/toto_ai/sports_stats/final_hybrid_comparison.py', 'src/toto_ai/sports_stats/final_hybrid_sidecar.py', 'src/toto_ai/sports_stats/parallel_g1.py', 'src/toto_ai/optimizer/exact_maximin_refinement.py', 'src/toto_ai/sports_stats/goal_probe_research.py']
source_hashes = {p: H(M/p) for p in source_files}
receipt_path = D/'G1_PROFILE_4998_NONFINAL_DIAGNOSTIC_RECEIPT.json'
receipt = {'task_id':'TOTOAI-4998-PARALLEL-INTEGRATION-20260906','status':'VALIDATED_NONFINAL_INPUT_STARTING','classification':'NONFINAL_PRE_DRAW_NONOPERATOR_RESEARCH_DIAGNOSTIC','source_cache':str(raw.path),'source_cache_file_sha256_at_freeze':prior['source_cache_file_sha256_at_freeze'],'source_payload_sha256':raw.payload_sha256,'source_fetched_at':raw.fetched_at.isoformat(),'input_path':str(snapshot.path),'snapshot_sha256':snapshot.snapshot_sha256,'snapshot_file_sha256':H(snapshot.path),'native_constructor':'byte-identical copy of previous native NONFINAL frozen envelope; not recreated or retimestamped', 'prior_receipt_sha256':prior_receipt_hash, 'prior_input_path':str(original_input), 'no_new_cache_read':True,'plan_id':plan.plan_id,'drawing':4998,'drawing_id':12102,'bank':4980,'stake':30,'seed':str(seed),'seed_file_sha256':H(seed),'seed_artifact_sha256':sports.artifact_sha256,'seed_as_of':sports.as_of.isoformat(),'output_dir':str(out),'started_at':now.isoformat(),'outer_timeout_seconds':480,'hard_stop_utc':'2026-09-06T14:28:00Z','protected_before':protected,'source_hashes':source_hashes,'automatic_wagering':False,'operator_compatible':False,'scheduler_final_input':False,'real_api_fetches':0,'db_writes':False,'operator_delivery':False}
receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
bootstrap = '''import os,sys\nfrom pathlib import Path\nROOT=Path(ROOT_VALUE).resolve()\nblocked=[]\ndef audit(event,args):\n    if event.startswith(('socket.connect','socket.getaddrinfo','socket.gethostby','socket.sendto','os.system','os.posix_spawn','os.exec')) or event=='sqlite3.connect':\n        blocked.append(event); raise PermissionError('Diagnostic denies network/database/escape: '+event)\n    if event=='subprocess.Popen' and Path(os.fsdecode(args[0])).resolve()!=Path(sys.executable).resolve():\n        raise PermissionError('Only native local Python worker allowed')\n    paths=[]\n    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):\n        p,mode,flags=args\n        if Path(os.fsdecode(p)).name.startswith('.env'): raise PermissionError('Secret reads forbidden')\n        if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):paths=[p]\n    elif event in ('os.mkdir','os.remove','os.rmdir','os.chmod','os.utime'):paths=[args[0]]\n    elif event in ('os.rename','os.link','os.symlink'):paths=[args[0],args[1]]\n    for p in paths:\n        if isinstance(p,(str,bytes,os.PathLike)) and Path(os.fsdecode(p)).resolve()!=Path('/dev/null') and not Path(os.fsdecode(p)).resolve().is_relative_to(ROOT): raise PermissionError('Diagnostic write outside owned root')\nsys.addaudithook(audit)\nGUARD=True\n'''.replace('ROOT_VALUE',repr(str(out)))
(out/'bootstrap/sitecustomize.py').write_text(bootstrap)
child = '''import functools,json,time,traceback\nfrom datetime import datetime,timezone\nfrom pathlib import Path\nimport sitecustomize\nfrom toto_ai.sports_stats import final_hybrid_comparison as c\nfrom toto_ai.sports_stats.parallel_g1 import ParallelG1Config\nassert sitecustomize.GUARD\nROOT=Path(ROOT_VALUE)\nstart=time.monotonic()\nsequence=0\ndef phase(name,state,**extra):\n    global sequence\n    sequence+=1\n    data={'phase':name,'state':state,'sequence':sequence,'elapsed_seconds':time.monotonic()-start,'observed_at':datetime.now(timezone.utc).isoformat(),**extra}\n    (ROOT/'phase.json').write_text(json.dumps(data))\n    print(json.dumps(data),flush=True)\nfor name in ['run_ev_crowd_current','select_uncertainty_package','select_robust_package','run_parallel_g1','package_quality_metrics']:\n    original=getattr(c,name)\n    def wrap(original,name):\n        @functools.wraps(original)\n        def call(*args,**kwargs):\n            extra={}\n            if name=='run_parallel_g1':extra={'N':len(kwargs['initial_coupons']),'U':len(set(kwargs['candidate_coupons'])),'M':len(kwargs['probability_models'])}\n            phase(name,'started',**extra)\n            result=original(*args,**kwargs)\n            details={}\n            if name=='run_parallel_g1':details={k:result.get(k) for k in ['status','reason','elapsed_seconds']}\n            phase(name,'completed',**details)\n            return result\n        return call\n    setattr(c,name,wrap(original,name))\nphase('comparison','started')\ntry:\n    report,paths=c.execute_final_hybrid_comparison(final_input_path=INPUT_VALUE,scheduler_plan_path=PLAN_VALUE,sports_artifact_path=SEED_VALUE,output_dir=ROOT/'comparison',deadline=start+470,g1_config=ParallelG1Config(family_refinement=True))\n    # Keep native hash-bound research report unchanged; no operator wrapper/publisher.\n    (ROOT/'comparison-return.json').write_text(json.dumps(report,indent=2))\n    phase('comparison','complete',automatic_wagering=False,operator_compatible=False)\nexcept BaseException as error:\n    (ROOT/'failure.json').write_text(json.dumps({'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()}))\n    phase('comparison','failed',error=type(error).__name__)\n    raise\nfinally:\n    (ROOT/'audit.json').write_text(json.dumps({'blocked':sitecustomize.blocked}))\n'''.replace('ROOT_VALUE',repr(str(out))).replace('INPUT_VALUE',repr(str(snapshot.path))).replace('PLAN_VALUE',repr(str(plan_path))).replace('SEED_VALUE',repr(str(seed)))
(out/'run-native-research.py').write_text(child)
env={'PATH':str(M/'.venv/bin')+':/usr/bin:/bin','HOME':str(out/'tmp'),'TMPDIR':str(out/'tmp'),'PYTHONPATH':str(out/'bootstrap')+':'+str(M/'src'),'PYTHONDONTWRITEBYTECODE':'1','NO_COLOR':'1','TERM':'dumb'}
stdout=(out/'stdout.log').open('xb');stderr=(out/'stderr.log').open('xb')
command=[sys.executable,'-B',str(out/'run-native-research.py')]
process=subprocess.Popen(command,cwd=M,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
receipt.update(status='RUNNING',pid=process.pid,command=command,stdout_path=str(out/'stdout.log'),stderr_path=str(out/'stderr.log'))
receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'status':'RUNNING','pid':process.pid,'output':str(out),'source_fetched_at':raw.fetched_at.isoformat(),'bound_pair':'NATIVE_VALIDATED'}),flush=True)
started=time.monotonic();last=-1;timed_out=False
while process.poll() is None:
    elapsed=time.monotonic()-started
    checkpoint={'elapsed_seconds':elapsed,'pid':process.pid,'state':'running','observed_at':datetime.now(timezone.utc).isoformat()}
    if (out/'phase.json').exists():
        try:checkpoint['phase']=json.loads((out/'phase.json').read_text())
        except json.JSONDecodeError:pass
    (D/'G1_PROFILE_MAIN_CHECKPOINT.json').write_text(json.dumps({**checkpoint,'output_dir':str(out),'receipt_path':str(receipt_path)},indent=2)+'\n');(out/'checkpoint.json').write_text(json.dumps(checkpoint,indent=2)+'\n');print(json.dumps(checkpoint),flush=True)
    if elapsed>=480 or datetime.now(timezone.utc)>=datetime(2026,9,6,14,28,tzinfo=timezone.utc):
        timed_out=True;os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        break
    time.sleep(15)
stdout.close();stderr.close()
assert H(original_input)==prior['snapshot_file_sha256'] and H(prior_path)==prior_receipt_hash, 'Prior immutable evidence changed'
receipt.update(status='TIMEOUT_RESEARCH_ONLY' if timed_out else ('COMPLETE_RESEARCH_ONLY' if process.returncode==0 else 'FAILED_RESEARCH_ONLY'),returncode=process.returncode,elapsed_seconds=time.monotonic()-started,completed_at=datetime.now(timezone.utc).isoformat(),protected_unchanged=all(H(Path(p))==h for p,h in protected.items()),source_unchanged=all(H(M/p)==h for p,h in source_hashes.items()),owned_processes=[])
if (out/'failure.json').exists():receipt['failure']=json.loads((out/'failure.json').read_text())
receipt_path.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['status','returncode','elapsed_seconds','protected_unchanged','source_unchanged']}),flush=True)
