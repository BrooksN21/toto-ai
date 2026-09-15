"""One exact saved-input EV run; no DB, network or operator export."""
import cProfile
import hashlib
import json
import signal
import socket
import sqlite3
import sys
import threading
import time
from dataclasses import asdict, replace
from pathlib import Path

def denied(*args, **kwargs):
    raise RuntimeError("offline replay forbids network/DB")

socket.socket.connect = denied
socket.create_connection = denied
sqlite3.connect = denied

from toto_ai.ev import package, ternary
from toto_ai.ev.drawing import effective_selection_budget
from toto_ai.ev.package_quality import PackageSelectionProvenance
from toto_ai.optimizer.strategy_comparison import run_ev_crowd_current
from toto_ai.optimizer.strategy_execution import frozen_input_from_snapshot
from toto_ai.runner.final_input import load_final_input
from toto_ai.runner.scheduler import load_scheduler_plan
from toto_ai.sports_stats.final_hybrid_comparison import _rebase_sports_probabilities
from toto_ai.sports_stats.probabilities import load_shadow_probability_artifact

ROOT = Path('/Users/turshevr/toto-ai')
OUT = Path(__file__).parent
label = sys.argv[1]
role = sys.argv[2] if len(sys.argv) > 2 else 'baseline'
bound = float(sys.argv[3]) if len(sys.argv) > 3 else 180
root = ROOT / 'reports/rehearsal/evening-4998-20260906T153000Z'
planpath = root / 'scheduler-plan.json'
inputpath = root / 'attempts/final-01-20260906T150005922935Z-6e7a4306/final-input.json'
seedpath = root / 'parallel-challenger/sports-seed/sports_probability_shadow_4998_ac04ea9b30359094.json'
plan = load_scheduler_plan(planpath)
snapshot = load_final_input(inputpath, expected_plan=plan)
assert snapshot.snapshot_sha256 == 'baea70824b1435bd771b5d9591ed6fb80319a89cacd25c77d9672e7503438282'
frozen = frozen_input_from_snapshot(snapshot, plan)
probability_hash = snapshot.probability_input_sha256
if role == 'sports':
    sports = load_shadow_probability_artifact(seedpath)
    rows = _rebase_sports_probabilities(frozen, sports.events)
    frozen = replace(frozen, events=tuple(replace(e, bk_probabilities=rows[e.event_order]) for e in frozen.events))
    inputpath = root / 'parallel-challenger/output/run-final-01-20260906T150005922935Z-6e7a4306/research-comparison/sports-final-probability-snapshot.json'
    probability_hash = json.loads(inputpath.read_text())['probability_input_sha256']
config = replace(plan.quality_v2_ev_config, effective_budget=effective_selection_budget(requested_bank=plan.requested_bank, pool_sum=frozen.pool_sum, stake=plan.stake))
provenance = PackageSelectionProvenance.from_artifacts(probability_snapshot_path=inputpath, probability_input_sha256=probability_hash, schedule_evidence_ledger_path=plan.schedule_evidence_ledger, scheduler_plan_path=planpath, selection_config=config)
start, cpu = time.monotonic(), time.process_time()
done = threading.Event()
phases = []
def emit(phase, **extra):
    data = {'phase':phase,'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu, **extra}
    phases.append(data)
    print(json.dumps(data), flush=True)
def heartbeat():
    while not done.wait(10): emit('heartbeat')
threading.Thread(target=heartbeat, daemon=True).start()
for mod, names in [(ternary, ['_crowd_qualifying_probabilities','ternary_convolve']), (package, ['rank_coupon_indices','_repair_selection','_improve_quality_selection','cover_14_bk_fill_seed'])]:
    for name in names:
        original = getattr(mod, name)
        def wrapper(*args, _f=original, _n=name, **kwargs):
            a,b = time.monotonic(),time.process_time()
            emit(_n+':start')
            result = _f(*args, **kwargs)
            emit(_n+':done',phase_wall=time.monotonic()-a,phase_cpu=time.process_time()-b)
            return result
        setattr(mod,name,wrapper)
def timeout(*args):
    raise TimeoutError('bounded offline profile wall limit')
signal.signal(signal.SIGALRM, timeout)
signal.setitimer(signal.ITIMER_REAL, bound)
profile = cProfile.Profile()
emit('start',role=role,wall_bound=bound,input_sha256=snapshot.snapshot_sha256)
result = None
failure = None
try:
    profile.enable()
    result = run_ev_crowd_current(frozen, config=config, provenance=provenance, component_builder=ternary.compute_ev_components, package_selector=package.select_ev_package_with_top_coupons)
except BaseException as exc:
    failure = {'type':type(exc).__name__,'message':str(exc)}
finally:
    profile.disable()
    signal.setitimer(signal.ITIMER_REAL,0)
    done.set()
    profile.dump_stats(str(OUT/(label+'.prof')))
    payload = {'label':label,'role':role,'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu,'failure':failure,'result':None if result is None else asdict(result),'phases':phases,'final_snapshot_sha256':snapshot.snapshot_sha256,'frozen_input_sha256':frozen.input_sha256,'config':asdict(config),'input_file_sha256':hashlib.sha256(inputpath.read_bytes()).hexdigest(),'operator_compatible':False,'automatic_wagering':False}
    (OUT/(label+'.json')).write_text(json.dumps(payload,indent=2))
    emit('finished',result_available=result is not None,failure=failure)
if failure: sys.exit(1)
