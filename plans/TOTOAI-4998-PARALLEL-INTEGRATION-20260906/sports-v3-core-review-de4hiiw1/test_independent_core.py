import importlib.util,json,math,copy
from pathlib import Path
import pytest
from toto_ai.sports_stats import v3_probability as v3, v3_parallel as par, v3_generation as gen
from dataclasses import asdict
W=Path(__file__).parent
def module(name):
 s=importlib.util.spec_from_file_location(name,W/'tests'/name);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
f=module('test_sports_v3_probability.py');g=module('test_sports_v3_generation.py')
proof={}
def test_current_bk_and_transform_frozen():
 model=f.fit();before=v3.canonical_json(model);r=f.feature(10);bk=[0.8,0.1,0.1]
 out=v3.infer_v3(model,r,bk_probabilities=bk,bk_input_sha256='d'*64,bk_margin=.7)
 assert out['status']=='PREDICTED_EXPERIMENTAL';assert v3.canonical_json(model)==before
 assert abs(sum(out['probabilities'])-1)<1e-12 and all(math.isfinite(p) and p>0 for p in out['probabilities'])
 assert sum(abs(a-b) for a,b in zip(bk,out['probabilities']))<=.2
 bad=copy.deepcopy(r);bad['source_rejected']=True;bad=v3.seal(bad);fallback=v3.infer_v3(model,bad,bk_probabilities=bk,bk_input_sha256='d'*64)
 assert fallback['status']=='BK_FALLBACK' and fallback['probabilities']==bk
 proof['numeric_current_bk_transform_fallback']='PASS'
@pytest.mark.parametrize('variant',['A3','A4'])
def test_future_training_label_rejected(variant):
 rows=f.training();rows[-1]['label']['available_at']='2099-01-01T00:00:00+00:00'
 with pytest.raises(ValueError,match='label availability'):f.fit(rows,variant=variant)
 proof['future_label_'+variant]='REJECTED'
def test_defect_serialized_training_chronology_not_validated():
 model=f.fit(variant='A4');model['training_rows'][0]['label_available_at']='2099-01-01T00:00:00+00:00';model=v3.seal(model)
 restored=v3.load_model(v3.canonical_json(model));out=v3.infer_v3(restored,f.feature(10))
 proof['serialization_future_label']={'available_at':model['training_rows'][0]['label_available_at'],'prediction_as_of':model['prediction_as_of'],'loader_accepted':True,'inference_status':out['status']}
 assert out['status']=='PREDICTED_EXPERIMENTAL'
def test_defect_generation_final_bk_identity_unbound():
 request,context=g.fixtures.request(),g.fixtures.context();inference=par.infer_final_bk(request,context);payload=asdict(g.frozen())
 for e in payload['events']:e['bk_probabilities']=(.8,.1,.1)
 result=gen.generate_v3_candidate(request=request,inference=inference,frozen_payload=payload,control_coupons=('1'*15,'X'*15,'2'*15),gate={'status':'SYNTHETIC_TEST_ONLY'})
 proof['generation_unbound_current_bk']={'inference_BK':context['bk_probabilities'][0],'generator_BK':list(payload['events'][0]['bk_probabilities']),'reported_final_input_sha256':result['final_input_sha256'],'generated_count':len(result['candidate_coupons']),'accepted':True}
 assert result['final_input_sha256']==context['final_input_sha256'] and len(result['candidate_coupons'])==3
def test_write_proof():
 (W/'independent-proof-rerun.json').write_text(json.dumps(proof,indent=2)+'\n')
