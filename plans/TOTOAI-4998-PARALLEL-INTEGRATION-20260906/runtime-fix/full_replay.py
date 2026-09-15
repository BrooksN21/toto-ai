import json,os,signal,threading,time,traceback
from datetime import datetime,timezone
from pathlib import Path
from toto_ai.sports_stats.final_hybrid_comparison import execute_final_hybrid_comparison
from toto_ai.sports_stats.parallel_g1 import ParallelG1Config
ROOT=Path('/Users/turshevr/toto-ai')
TASK=ROOT/'plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/runtime-fix'
OUT=TASK/('full-replay-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
OUT.mkdir()
r=ROOT/'reports/rehearsal/evening-4998-20260906T153000Z'
start,cpu=time.perf_counter(),time.process_time()
done=threading.Event()
(OUT/'owner.json').write_text(json.dumps({'pid':os.getpid(),'started_at':datetime.now(timezone.utc).isoformat(),'deadline_seconds':360,'outer_bound_seconds':420,'operator_compatible':False,'automatic_wagering':False}))
print(json.dumps({'started':str(OUT),'pid':os.getpid()}),flush=True)
def heartbeat():
 while not done.wait(10): print(json.dumps({'phase':'owned_research_heartbeat','wall':time.perf_counter()-start,'parent_cpu':time.process_time()-cpu}),flush=True)
threading.Thread(target=heartbeat,daemon=True).start()
def timeout(*a): raise TimeoutError('offline outer wall bound420s')
signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,420)
try:
 report,paths=execute_final_hybrid_comparison(final_input_path=r/'attempts/final-01-20260906T150005922935Z-6e7a4306/final-input.json',scheduler_plan_path=r/'scheduler-plan.json',sports_artifact_path=r/'parallel-challenger/sports-seed/sports_probability_shadow_4998_ac04ea9b30359094.json',output_dir=OUT/'comparison',deadline=start+360,g1_config=ParallelG1Config(family_refinement=True))
 old=json.loads((r/'parallel-challenger/output/run-final-01-20260906T150005922935Z-6e7a4306/research-comparison/comparison.json').read_text())
 comparisons={k:{'same_package':old[k]['package_sha256']==report[k]['package_sha256'],'same_p13_p14_p15':all(old[k][x]==report[k][x] for x in ['p13','p14','p15'])} for k in ['baseline','sports']}
 summary={'status':'COMPLETE_RESEARCH_ONLY','wall_seconds':time.perf_counter()-start,'parent_cpu_seconds':time.process_time()-cpu,'report':str(paths.report),'same_final_input':report['final_input_snapshot_sha256']==old['final_input_snapshot_sha256'],'ev_equivalence':comparisons,'quality_v3_candidate_count':report['quality_v3']['candidate_count'],'robust_candidate_count':report['robust']['candidate_count'],'selection':report['experimental_selection'],'g1':report['g1_research_refinement'],'control_recomputed':True,'operator_compatible':False,'automatic_wagering':False}
 (OUT/'receipt.json').write_text(json.dumps(summary,indent=2))
 print(json.dumps({k:v for k,v in summary.items() if k not in ['selection','g1']}),flush=True)
except BaseException as error:
 (OUT/'failure.json').write_text(json.dumps({'type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc(),'wall_seconds':time.perf_counter()-start}))
 print(json.dumps({'failed':type(error).__name__,'error':str(error)}),flush=True)
 raise
finally:
 done.set();signal.setitimer(signal.ITIMER_REAL,0)
