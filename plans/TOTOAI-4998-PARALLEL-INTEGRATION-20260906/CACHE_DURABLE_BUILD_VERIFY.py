import json,hashlib,tempfile,subprocess,difflib,shutil
from pathlib import Path
from datetime import datetime
root=Path('/Users/turshevr/toto-ai');task=root/'plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906';old=task/'CACHE_ATOMIC_CANDIDATE';dest=task/'CACHE_DURABLE_CANDIDATE';assert not dest.exists();rec=json.loads((task/'CACHE_ATOMIC_IMPLEMENTATION_RECEIPT.json').read_text());m=rec['manifest'];sha=lambda b:hashlib.sha256(b).hexdigest();original={x['path']:(old/x['path']).read_bytes() for x in m['changes']}
for x in m['changes']:assert sha(original[x['path']])==x['after_sha256']
source=original['src/toto_ai/sports_stats/goal_probe_collection.py'].decode();source=source.replace('_publish_retry_record(claim_path, _pretty(claim), exclusive=True)','_publish_retry_record(\n        claim_path, _pretty(claim), durable_root=output, exclusive=True\n    )').replace('_publish_retry_record(generation / "outcome.json", _pretty(outcome))','_publish_retry_record(\n            generation / "outcome.json", _pretty(outcome), durable_root=output\n        )',1)
source=source.replace('    _publish_retry_record(generation / "outcome.json", _pretty(outcome))','    _publish_retry_record(\n        generation / "outcome.json", _pretty(outcome), durable_root=output\n    )')
source=source.replace('    path: Path, content: bytes, *, exclusive: bool = False','    path: Path, content: bytes, *, durable_root: Path, exclusive: bool = False')
anchor='''    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if exclusive:''';assert source.count(anchor)==1;source=source.replace(anchor,'''    if not path.parent.is_relative_to(durable_root):
        raise ValueError("retry publication escapes durability root")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if exclusive:''')
source=source.replace('''            raise ValueError(f"GOAL probe artifact conflict: {path}")
        return
    pending =''','''            raise ValueError(f"GOAL probe artifact conflict: {path}")
        _sync_retry_directories(path.parent, durable_root)
        return
    pending =''')
anchor='''    os.link(pending, path)


def _capture_goal_probe_input''';new='''    os.link(pending, path)
    _sync_retry_directories(path.parent, durable_root)


def _sync_retry_directories(directory: Path, durable_root: Path) -> None:
    # Bottom-up syncing persists the final link and every newly-created ancestor
    # through the already-existing cache root, before collection or acknowledgement.
    while True:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        if directory == durable_root:
            return
        directory = directory.parent


def _capture_goal_probe_input''';assert source.count(anchor)==1;source=source.replace(anchor,new)
tests='''

def test_retry_directory_sync_order_before_collection(monkeypatch, tmp_path):
    output = _cache_fixture(tmp_path)
    _cache_refresh_stub(monkeypatch, tmp_path)
    original_collect = goal_probe_collection._capture_goal_probe_input
    original_open = goal_probe_collection.os.open
    original_close = goal_probe_collection.os.close
    original_sync = goal_probe_collection.os.fsync
    original_link = goal_probe_collection.os.link
    descriptors = {}
    calls = []

    def open_directory(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        descriptors[fd] = Path(path)
        return fd

    def close_directory(fd):
        descriptors.pop(fd, None)
        return original_close(fd)

    def sync(fd):
        calls.append(("dir", descriptors[fd]) if fd in descriptors else ("file", None))
        return original_sync(fd)

    def link(src, dst):
        calls.append(("link", Path(dst)))
        return original_link(src, dst)

    def collect(**kwargs):
        calls.append(("collector", None))
        return original_collect(**kwargs)

    monkeypatch.setattr(goal_probe_collection.os, "open", open_directory)
    monkeypatch.setattr(goal_probe_collection.os, "close", close_directory)
    monkeypatch.setattr(goal_probe_collection.os, "fsync", sync)
    monkeypatch.setattr(goal_probe_collection.os, "link", link)
    monkeypatch.setattr(goal_probe_collection, "_capture_goal_probe_input", collect)
    _ensure_cached(tmp_path, output, 15, request_budget=3)
    marker = calls.index(("collector", None))
    claim = next(path for kind, path in calls if kind == "link")
    expected_dirs = []
    directory = claim.parent
    while True:
        expected_dirs.append(("dir", directory))
        if directory == output:
            break
        directory = directory.parent
    assert calls[:marker] == [("file", None), ("link", claim), *expected_dirs]
    assert calls[marker + 1:] == [
        ("file", None), ("link", claim.parent / "outcome.json"), *expected_dirs,
    ]


@pytest.mark.parametrize("failure_phase", ["attempt.json", "outcome.json"])
def test_directory_sync_error_does_not_acknowledge(monkeypatch, tmp_path, failure_phase):
    import stat

    output = _cache_fixture(tmp_path)
    collections = _cache_refresh_stub(monkeypatch, tmp_path)
    original_sync = goal_probe_collection.os.fsync
    original_link = goal_probe_collection.os.link
    phase = None

    def link(src, dst):
        nonlocal phase
        phase = Path(dst).name
        return original_link(src, dst)

    def sync(fd):
        if phase == failure_phase and stat.S_ISDIR(goal_probe_collection.os.fstat(fd).st_mode):
            raise OSError("injected directory fsync failure")
        return original_sync(fd)

    monkeypatch.setattr(goal_probe_collection.os, "link", link)
    monkeypatch.setattr(goal_probe_collection.os, "fsync", sync)
    with pytest.raises(OSError, match="injected directory fsync failure"):
        _ensure_cached(tmp_path, output, 15, request_budget=3)
    assert len(collections) == (0 if failure_phase == "attempt.json" else 1)
    claims = list(output.glob("failed-cache-retry/*/attempts/*/attempt.json"))
    assert len(claims) == 1
    assert json.loads(claims[0].read_text())["request_budget"] == 3
'''
# Keep existing candidate tests intact; format only the new test chunk.
fmt=subprocess.run([str(root/'.venv/bin/ruff'),'format','--stdin-filename','new_tests.py','-'],input=tests,text=True,capture_output=True,cwd=root,timeout=10,check=True).stdout
tmp=Path(tempfile.mkdtemp(prefix='toto-cache-durable-')).resolve();(tmp/'bootstrap').mkdir();(tmp/'overlay/sports_stats').mkdir(parents=True)
h=rec['harness'];(tmp/'bootstrap/sitecustomize.py').write_text(h['bootstrap']);shutil.copyfile(Path(h['temporary_root'])/'cache_review_fixture.py',tmp/'cache_review_fixture.py');(tmp/'overlay/cli.py').write_bytes(original['src/toto_ai/cli.py']);(tmp/'overlay/sports_stats/goal_probe_collection.py').write_bytes(original['src/toto_ai/sports_stats/goal_probe_collection.py']);(tmp/'test_corrected_targeted.py').write_bytes(original['tests/test_goal_probe_collection.py']+fmt.encode())
runner=h['green_runner'].replace(h['temporary_root'],str(tmp));addition=f", {str(tmp/'test_corrected_targeted.py')!r} + '::test_retry_directory_sync_order_before_collection', {str(tmp/'test_corrected_targeted.py')!r} + '::test_directory_sync_error_does_not_acknowledge'";runner=runner.replace("])\nimports=",addition+"])\nimports=");env=dict(h['environment']);env.update(HOME=str(tmp),TMPDIR=str(tmp),PYTHONPATH=f'{tmp}/bootstrap:{tmp}:{root}/src');(tmp/'red.py').write_text(runner.replace('pytest-green','pytest-red'));py=str(root/'.venv/bin/python');red=subprocess.run([py,'-B',str(tmp/'red.py')],cwd=root,env=env,capture_output=True,text=True,timeout=25);print('RED',red.returncode,red.stdout,red.stderr,flush=True);assert red.returncode==1 and '3 failed, 18 passed' in red.stdout
(tmp/'overlay/sports_stats/goal_probe_collection.py').write_text(source);(tmp/'green.py').write_text(runner);green=subprocess.run([py,'-B',str(tmp/'green.py')],cwd=root,env=env,capture_output=True,text=True,timeout=25);print('GREEN',green.returncode,green.stdout,green.stderr,flush=True);assert green.returncode==0 and '21 passed' in green.stdout
candidate=dict(original);candidate['src/toto_ai/sports_stats/goal_probe_collection.py']=source.encode();candidate['tests/test_goal_probe_collection.py']+=fmt.encode();candidate['knowledge/goal_probe_failed_cache_boundary.md']+=b'\nDurability amendment: after file fsync and exclusive hard-link publication, sync\nthe final-name directory then each ancestor bottom-up through the existing cache\noutput root. Directory-sync errors propagate before collector entry or outcome\nacknowledgement. This verifies filesystem calls/order, not real power-loss behavior.\n'
for n,b in candidate.items():p=dest/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
ruff=subprocess.run([str(root/'.venv/bin/ruff'),'check','--no-cache','--config',str(root/'pyproject.toml'),str(dest/'src/toto_ai/sports_stats/goal_probe_collection.py'),str(dest/'src/toto_ai/cli.py'),str(dest/'tests/test_goal_probe_collection.py'),str(task/'test_failed_goal_cache_atomic_publication.py')],cwd=root,env=env,capture_output=True,text=True,timeout=15);print('RUFF',ruff.returncode,ruff.stdout,flush=True);assert ruff.returncode==0
# Preserve the original before authority, including CLI; never silently rebase to concurrent G1.
full='';delta='';mismatches=[]
for x in m['changes']:
 n=x['path'];p=root/n;b=p.read_bytes() if p.exists() else None
 if (None if b is None else sha(b))!=x['before_sha256']:mismatches.append(n)
 # Original full patch is preserved; new full replacement composed against original guarded bytes.
 if n=='src/toto_ai/cli.py' and n in mismatches:
  from importlib.util import spec_from_file_location,module_from_spec
  raise RuntimeError('CLI before changed: retain candidate; final manifest assembly requires original before reconstruction')
 assert (None if b is None else sha(b))==x['before_sha256'],n
 full+=''.join(difflib.unified_diff((b or b'').decode().splitlines(True),candidate[n].decode().splitlines(True),fromfile='/dev/null' if b is None else 'a/'+n,tofile='b/'+n));delta+=''.join(difflib.unified_diff(original[n].decode().splitlines(True),candidate[n].decode().splitlines(True),fromfile='a/'+n,tofile='b/'+n));x['after_sha256']=sha(candidate[n])
for x in m['dependencies']:
 if sha((root/x['path']).read_bytes())!=x['before_sha256']:mismatches.append(x['path'])
pp=task/'CACHE_DURABLE_CANDIDATE.patch';pp.write_text(full);(task/'CACHE_DURABLE_DELTA_FROM_75BD.patch').write_text(delta);m['patch_file']=pp.name;m['patch_sha256']=sha(pp.read_bytes());(task/'CACHE_DURABLE_CANDIDATE_MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n')
result={'task_id':'TOTOAI-4998-PARALLEL-INTEGRATION-20260906','phase':'DURABILITY_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_REVIEW','completed_at':datetime.now().astimezone().isoformat(),'patch_sha256':m['patch_sha256'],'delta_sha256':sha(delta.encode()),'original_candidate_unchanged':all((old/n).read_bytes()==b for n,b in original.items()),'cli_candidate_unchanged':candidate['src/toto_ai/cli.py']==original['src/toto_ai/cli.py'],'current_guard_mismatches':mismatches,'red':{'exit':red.returncode,'stdout':red.stdout},'green':{'exit':green.returncode,'stdout':green.stdout},'ruff':{'exit':ruff.returncode,'stdout':ruff.stdout},'harness':{'bootstrap':h['bootstrap'],'runner':runner,'environment':env,'temporary_root':str(tmp)},'runtime':json.loads((tmp/'runtime.json').read_text()),'applied':False,'activated':False,'published':False,'claim':'Filesystem durability calls/order/error paths verified; no real power-loss experiment','next':'Euler independent review; separate CLI composition/main apply afterward'};(task/'CACHE_DURABLE_IMPLEMENTATION_RECEIPT.json').write_text(json.dumps(result,indent=2)+'\n');print('DONE',result['completed_at'],result['patch_sha256'],mismatches,flush=True)
