"""Every register head entry gets a hook-payload pair or an explicit third state."""
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT/'tests/fixtures/goal.json').read_text())
sys.path.insert(0, str(ROOT/'plugin'))
EVALUABLE = [c for c in CASES if c['state'] == 'EVALUABLE']
ROUTINE = json.loads((ROOT/'tests/fixtures/honest_writes.json').read_text())


def run_payloads(case, side, directory):
    directory.mkdir()
    for name, text in dict(case.get('files', {}), **case.get(side+'_files', {})).items():
        target = directory/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    if case.get('tables'):
        # JSON strings and arrays are valid TOML values for these named tables.
        (directory/'makoto.toml').write_text('[named_sets]\n'+'\n'.join(
            key+' = '+json.dumps(value) for key,value in case['tables'].items())+'\n')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', MAKOTO_STATE_DIR=str(directory/'state'))
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    response = None
    for event in case[side]:
        payload = dict(event, session_id='goal', cwd=str(directory))
        result = subprocess.run([sys.executable,'-s','-m','makoto2'],
            cwd=ROOT/'plugin', env=env, input=json.dumps(payload), capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert not result.stderr, result.stderr
        response = json.loads(result.stdout)
        if event is not case[side][-1]:
            assert response == {}, response
    return response


@pytest.mark.parametrize('case', EVALUABLE, ids=[c['id'] for c in EVALUABLE])
def test_fake(case, tmp_path):
    fake = run_payloads(case, 'fake', tmp_path/'fake')
    assert fake, fake
    if case['fake'][-1]['hook_event_name'] == 'PreToolUse':
        reason = fake['hookSpecificOutput']['permissionDecisionReason']
        assert fake['hookSpecificOutput']['permissionDecision'] == 'deny'
    else:
        assert fake['decision'] == 'block'
        reason = fake['reason']
    assert re.search(r'\b'+case['id']+r'\b', reason), reason


@pytest.mark.parametrize('case', EVALUABLE, ids=[c['id'] for c in EVALUABLE])
def test_honest(case, tmp_path):
    assert run_payloads(case, 'honest', tmp_path/'honest') == {}


@pytest.mark.parametrize('case', ROUTINE, ids=[c['id'] for c in ROUTINE])
def test_routine_honest(case, tmp_path):
    assert run_payloads(case, 'honest', tmp_path/'routine') == {}


def test_nonexistent_path_is_not_unread(tmp_path):
    from makoto2 import evaluate, observed
    path = str(tmp_path/'new.txt')
    record = observed.record([dict(hook_event_name='PostToolUse', tool_name='Glob',
                                  tool_input={'pattern':'*.txt'}, tool_response=path)])
    event = dict(hook_event_name='PreToolUse', cwd=str(tmp_path), tool_name='Write',
                 tool_input={'file_path':str(tmp_path/'index.md'), 'content':path})
    assert not evaluate.write_owes({}, {}, record, event)


def test_register_population_and_third_state():
    text = (ROOT/'REGISTER.md').read_text()
    heads = text[text.index('===== 1 -'):text.index('===== MERGES MADE')]
    ids = re.findall(r'^([A-H]\d+)\s', heads, re.M)
    assert len(ids) == 74
    assert sorted(ids) == sorted(c['id'] for c in CASES)
    for case in CASES:
        assert case['state'] in ('EVALUABLE','NOT-EVALUABLE')
        if case['state'] == 'NOT-EVALUABLE':
            assert case['reason'] and 'fake' not in case and 'honest' not in case
        else:
            module, function = case['predicate'].split('.')
            assert callable(getattr(importlib.import_module('makoto2.'+module),function))
            assert case['fake'] and case['honest']
