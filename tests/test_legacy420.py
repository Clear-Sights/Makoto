"""The restored release stays importable, executable, and present in packages."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'plugin/legacy420'


def check_snapshot(snapshot):
    manifest = json.loads((snapshot / 'SOURCE.json').read_text())
    assert manifest['source_ref'] == 'e8032ec650e2e0361fecc31342ecff16b1e1994d'
    assert len(manifest['files']) == 129
    for entry in manifest['files']:
        path = snapshot / entry['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], entry['path']
        if os.name != 'nt' and entry['mode'] == '100755':
            assert os.access(path, os.X_OK), entry['path']


def legacy_smoke(snapshot, state):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', MAKOTO_STATE_DIR=str(state))
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    # A separate interpreter resolves the original absolute makoto2 imports.
    # Import all runtime and test files, including the opt-in acceptance tasks.
    script = '''
import importlib, pathlib, sys
root = pathlib.Path.cwd()
sys.path[:0] = [str(root / 'plugin'), str(root / 'tests'), str(root / 'mesh')]
for path in sorted((root / 'plugin/makoto2').glob('*.py')):
    importlib.import_module('makoto2' if path.stem == '__init__' else 'makoto2.' + path.stem)
for path in sorted((root / 'tests').glob('*.py')):
    importlib.import_module(path.stem)
from makoto2 import evaluate, observed
here = root / 'plugin/makoto2'
cfg = evaluate.load_cfg(str(here / 'config.json'))
rows = evaluate.load_rows(str(here / 'rows.tsv'), cfg)
event = {'hook_event_name': 'PreToolUse', 'tool_name': 'Write',
         'tool_input': {'file_path': 'source.py', 'content': 'match value:\\n case 1: print(value)'}}
finding = evaluate.evaluate(rows, observed.record([]), event)
assert finding and finding['row'] == 'SWITCH.fallthrough', finding
event['tool_input']['content'] += '\\n case _: raise ValueError()'
assert evaluate.evaluate(rows, observed.record([]), event) is None
'''
    result = subprocess.run([sys.executable, '-I', '-c', script], cwd=snapshot,
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = dict(hook_event_name='PreToolUse', session_id='legacy-smoke',
                   tool_name='Write', tool_input=dict(file_path='source.py',
                   content='match value:\n case 1: print(value)'))
    result = subprocess.run([sys.executable, '-s', '-m', 'makoto2'],
                            cwd=snapshot / 'plugin', env=env, input=json.dumps(payload),
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    decision = json.loads(result.stdout)['hookSpecificOutput']
    assert decision['permissionDecision'] == 'deny'
    assert 'C5' in decision['permissionDecisionReason']


def test_legacy_source_bytes():
    check_snapshot(SNAPSHOT)


def test_legacy_imports_and_hook(tmp_path):
    legacy_smoke(SNAPSHOT, tmp_path / 'source-state')


def test_legacy_ships_and_runs_in_current_package(tmp_path):
    sys.path.insert(0, str(ROOT / 'plugin'))
    from makoto2 import build_package
    result = build_package(ROOT, tmp_path / 'package')
    snapshot = Path(result['path']) / 'legacy420'
    check_snapshot(snapshot)
    legacy_smoke(snapshot, tmp_path / 'package-state')
