"""Build a review-only exact candidate and bounded offline evidence."""
import difflib
import hashlib
import importlib.util
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MAIN = Path('/Users/turshevr/toto-ai')
D = MAIN / 'plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906'
R = Path('/Users/turshevr/.codex/worktrees/ab34/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906')
V = R.parent / 'TOTOAI-4996-4997-RECOVERY-20260904/VERIFY_MAIN_INTEGRATION.py'
spec = importlib.util.spec_from_file_location('verifier', V)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
m = json.loads((R / 'FAILED_GOAL_CACHE_CORRECTED_MANIFEST.json').read_text())
old_patch = (R / m['patch_file']).read_bytes()
assert v.sha256(old_patch) == 'f817f2d6a986c4c06c824500e0cb78441928a94a5db839197a1435eb1062368f'
before = {}
rebased = []
for row in m['changes'] + m['dependencies']:
    p = v.checked_path(MAIN, row['path'])
    before[row['path']] = p.read_bytes() if p.exists() else None
    actual = None if before[row['path']] is None else v.sha256(before[row['path']])
    if actual != row['before_sha256']:
        assert row in m['dependencies'], ('target changed', row['path'])
        rebased.append({'path': row['path'], 'old': row['before_sha256'], 'current': actual})
        row['before_sha256'] = actual
candidate = v.reconstruct(old_patch, before)
for row in m['changes']:
    assert v.sha256(candidate[row['path']]) == row['after_sha256']
prior = json.loads((D / 'FAILED_GOAL_CACHE_CORRECTION_INDEPENDENT_REVIEW.json').read_text())
tmp = Path(tempfile.mkdtemp(prefix='toto-cache-atomic-'))
(tmp / 'bootstrap').mkdir()
(tmp / 'overlay/sports_stats').mkdir(parents=True)
probe = (D / 'test_failed_goal_cache_correction_review.py').read_text()
probe = probe.replace('path.name == interrupted_file', '(path.name == interrupted_file or path.name.startswith("." + interrupted_file + "."))')
probe = probe.replace('        if not interrupted and (path.name == interrupted_file or path.name.startswith("." + interrupted_file + ".")) and mode in {"xb", "wb"}:', '        target = path.name == interrupted_file or path.name.startswith(\n            "." + interrupted_file + "."\n        )\n        if not interrupted and target and mode in {"xb", "wb"}:')
probe_path = D / 'test_failed_goal_cache_atomic_publication.py'
probe_path.write_text(probe)
for src, dst in [('src/toto_ai/sports_stats/goal_probe_collection.py', 'overlay/sports_stats/goal_probe_collection.py'), ('src/toto_ai/cli.py', 'overlay/cli.py'), ('tests/test_goal_probe_collection.py', 'test_corrected_targeted.py')]:
    (tmp / dst).write_bytes(candidate[src])
frozen = R / '.failed-cache-verification/original_cache_review_fixture.py'
assert v.sha256(frozen.read_bytes()) == '5a9d8d3b637929aa08f977578b3eda38c877d6436bbabb190ac36fdb875a0094'
(tmp / 'cache_review_fixture.py').write_bytes(frozen.read_bytes())
bootstrap = prior['harness']['bootstrap']
(tmp / 'bootstrap/sitecustomize.py').write_text(bootstrap)
runner = prior['harness']['runner'].replace(prior['temporary_overlay'], str(tmp)).replace('test_failed_goal_cache_correction_review.py', 'test_failed_goal_cache_atomic_publication.py')
runner = runner.replace(str(tmp / 'pytest-final'), str(tmp / 'pytest-red'))
(tmp / 'run-red.py').write_text(runner)
env = dict(prior['harness']['environment'])
env.update(HOME=str(tmp), TMPDIR=str(tmp), PYTHONPATH=str(tmp / 'bootstrap') + ':' + str(tmp) + ':' + str(MAIN / 'src'))
python = str(MAIN / '.venv/bin/python')
red = subprocess.run([python, '-B', str(tmp / 'run-red.py')], cwd=MAIN, env=env, capture_output=True, text=True, timeout=25)
assert red.returncode == 1 and '2 failed, 16 passed' in red.stdout, red.stdout + red.stderr
print('RED: 2 failed /16 passed', flush=True)
source = candidate['src/toto_ai/sports_stats/goal_probe_collection.py'].decode()
source = source.replace('import json\n', 'import json\nimport os\n')
source = source.replace('from typing import Any\n', 'from typing import Any\nfrom uuid import uuid4\n')
old_claim = '    with claim_path.open("xb") as stream:\n        stream.write(_pretty(claim))'
assert source.count(old_claim) == 1
source = source.replace(old_claim, '    _publish_retry_record(claim_path, _pretty(claim), exclusive=True)')
assert source.count('_write_exact(generation / "outcome.json", _pretty(outcome))') == 2
source = source.replace('_write_exact(generation / "outcome.json", _pretty(outcome))', '_publish_retry_record(generation / "outcome.json", _pretty(outcome))')
helper = '''def _publish_retry_record(
    path: Path, content: bytes, *, exclusive: bool = False
) -> None:
    """Publish complete retry metadata without exposing partial committed JSON.

    Staging files are append-only evidence. No provider request starts before the
    claim is linked; an interrupted outcome leaves the complete claim recoverable.
    The enclosing flock remains held throughout publication and collection.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if exclusive:
            raise FileExistsError(f"GOAL probe retry claim already exists: {path}")
        if path.read_bytes() != content:
            raise ValueError(f"GOAL probe artifact conflict: {path}")
        return
    pending = path.with_name(f".{path.name}.{uuid4().hex}.pending")
    with pending.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    # Same-directory hard-link publication is atomic and cannot replace evidence.
    os.link(pending, path)


'''
assert source.count('def _capture_goal_probe_input(') == 1
source = source.replace('def _capture_goal_probe_input(', helper + 'def _capture_goal_probe_input(')
candidate['src/toto_ai/sports_stats/goal_probe_collection.py'] = source.encode()
# Embed portable tests in the candidate test module; original reviewer files stay intact.
test_body = probe[probe.index('@pytest.mark.parametrize'):]
test_body = test_body.replace('fixture.', '').replace('candidate.', 'goal_probe_collection.')
candidate['tests/test_goal_probe_collection.py'] += ('\n\n' + test_body).encode()
candidate['knowledge/goal_probe_failed_cache_boundary.md'] += b'\nClaim and outcome publication is crash-safe: complete fsynced bytes are linked\natomically from same-directory append-only .pending staging files. Link creation\nnever replaces existing evidence. Incomplete unpublished staging is not a claim\nand cannot precede provider requests; interrupted outcomes retain the full claim\nreservation and use existing lease recovery. Other record formats are unchanged.\n'
(tmp / 'overlay/sports_stats/goal_probe_collection.py').write_bytes(candidate['src/toto_ai/sports_stats/goal_probe_collection.py'])
(tmp / 'test_corrected_targeted.py').write_bytes(candidate['tests/test_goal_probe_collection.py'])
green_runner = runner.replace(str(tmp / 'pytest-red'), str(tmp / 'pytest-green'))
(tmp / 'run-green.py').write_text(green_runner)
green = subprocess.run([python, '-B', str(tmp / 'run-green.py')], cwd=MAIN, env=env, capture_output=True, text=True, timeout=25)
print(green.stdout, green.stderr, flush=True)
assert green.returncode == 0 and '18 passed' in green.stdout
runtime = json.loads((tmp / 'runtime.json').read_text())
assert not runtime['blocked_actions']
# Preserve current source/CLI and old evidence; candidate only under this task.
bundle = D / 'CACHE_ATOMIC_CANDIDATE'
for rel, data in candidate.items():
    dest = bundle / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
ruff_command = [str(MAIN / '.venv/bin/ruff'), 'check', '--no-cache', '--config', str(MAIN / 'pyproject.toml'), str(bundle / 'src/toto_ai/sports_stats/goal_probe_collection.py'), str(bundle / 'src/toto_ai/cli.py'), str(bundle / 'tests/test_goal_probe_collection.py'), str(probe_path)]
ruff = subprocess.run(ruff_command, cwd=MAIN, env=env, capture_output=True, text=True, timeout=15)
print('RUFF', ruff.returncode, ruff.stdout, flush=True)
assert ruff.returncode == 0
patch_text = ''
delta_text = ''
old_candidate = v.reconstruct(old_patch, before)
for rel, data in candidate.items():
    patch_text += ''.join(difflib.unified_diff((before[rel] or b'').decode().splitlines(keepends=True), data.decode().splitlines(keepends=True), fromfile='/dev/null' if before[rel] is None else 'a/' + rel, tofile='b/' + rel))
    delta_text += ''.join(difflib.unified_diff(old_candidate[rel].decode().splitlines(keepends=True), data.decode().splitlines(keepends=True), fromfile='a/' + rel, tofile='b/' + rel))
patch_path = D / 'CACHE_ATOMIC_CANDIDATE.patch'; patch_path.write_text(patch_text)
(D / 'CACHE_ATOMIC_DELTA_FROM_F817.patch').write_text(delta_text)
m['patch_file'] = patch_path.name; m['patch_sha256'] = v.sha256(patch_path.read_bytes())
for row in m['changes']: row['after_sha256'] = v.sha256(candidate[row['path']])
v.read_guarded(MAIN, m)
head = subprocess.run([str(MAIN / 'scripts/project-git'), 'rev-parse', 'HEAD'], cwd=MAIN, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
m['expected_head'] = head
manifest_path = D / 'CACHE_ATOMIC_CANDIDATE_MANIFEST.json'; manifest_path.write_text(json.dumps(m, indent=2) + '\n')
mechanical = v.verify(MAIN, m, patch_path.read_bytes(), head=head)
receipt = {'task_id':'TOTOAI-4998-PARALLEL-INTEGRATION-20260906', 'status':'IMPLEMENTED_CANDIDATE_REVIEW_PENDING_NOT_APPLIED', 'completed_at':datetime.now(timezone.utc).isoformat(), 'manifest':m, 'rebound_dependencies':rebased, 'original_candidate_sha256':v.sha256(old_patch), 'delta_sha256':v.sha256(delta_text.encode()), 'red':{'exit_code':red.returncode,'stdout':red.stdout,'stderr':red.stderr}, 'green':{'exit_code':green.returncode,'stdout':green.stdout,'stderr':green.stderr}, 'ruff':{'exit_code':ruff.returncode,'command':ruff_command,'stdout':ruff.stdout}, 'runtime':runtime, 'harness':{'bootstrap':bootstrap,'red_runner':runner,'green_runner':green_runner,'environment':env,'temporary_root':str(tmp)}, 'mechanical_guard':mechanical, 'main_files_unchanged':True, 'old_review_probe_sha256':v.sha256((D / 'test_failed_goal_cache_independent_review.py').read_bytes()), 'old_crash_probe_sha256':v.sha256((D / 'test_failed_goal_cache_correction_review.py').read_bytes()), 'atomic_probe_sha256':v.sha256(probe_path.read_bytes()), 'no_network_db_jobs_activation':True}
(D / 'CACHE_ATOMIC_IMPLEMENTATION_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('CANDIDATE', m['patch_sha256'], mechanical, flush=True)
