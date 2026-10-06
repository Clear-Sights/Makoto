"""Independent ordinary-session corpus: every evaluated fake must name its head."""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT/'tests/fixtures/tells.json').read_text())
PAIRS = [(case, index, pair) for case in CASES for index, pair in enumerate(case.get('pairs', []))]


def run_session(pair, side, directory):
    directory.mkdir(parents=True)
    for path, content in pair.get(side+'_files', {}).items():
        target = directory/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    if pair.get('tables'):
        (directory/'makoto.toml').write_text('[named_sets]\n'+'\n'.join(
            key+' = '+json.dumps(value) for key, value in pair['tables'].items())+'\n')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', MAKOTO_STATE_DIR=str(directory/'state'))
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    results = []
    for event in pair[side]:
        payload = dict(event, session_id='tells', cwd=str(directory))
        result = subprocess.run([sys.executable, '-s', '-m', 'makoto2'], cwd=ROOT/'plugin',
            env=env, input=json.dumps(payload), capture_output=True, text=True)
        assert result.returncode == 0 and not result.stderr, result.stderr
        results.append(json.loads(result.stdout))
    return results


def reason(response):
    return response.get('reason', response.get('hookSpecificOutput', {}).get('permissionDecisionReason', ''))


@pytest.mark.parametrize('case,index,pair', PAIRS, ids=[c['id']+'-'+str(i+1) for c,i,p in PAIRS])
def test_fake_caught_and_named(case, index, pair, tmp_path):
    results = run_session(pair, 'fake', tmp_path/'fake')
    assert not any(results[:-1]), results
    assert results[-1], results
    assert re.search(r'\b'+case['id']+r'\b', reason(results[-1])), results[-1]


@pytest.mark.parametrize('case,index,pair', PAIRS, ids=[c['id']+'-'+str(i+1) for c,i,p in PAIRS])
def test_honest_silent(case, index, pair, tmp_path):
    assert not any(run_session(pair, 'honest', tmp_path/'honest'))


def test_register_and_tell_population():
    register = (ROOT/'REGISTER.md').read_text()
    heads = register[register.index('===== 1 -'):register.index('===== MERGES MADE')]
    ids = re.findall(r'^([A-H]\d+)\s', heads, re.M)
    tells = list(csv.DictReader((ROOT/'mesh/TELLS.tsv').open(), delimiter='\t'))
    assert sorted(ids) == sorted(c['id'] for c in CASES) == sorted(t['id'] for t in tells)
    for case, tell in zip(CASES, tells):
        assert case['id'] == tell['id'] and case['state'] == tell['state']
        assert tell['description'] and tell['fix'] and tell['needs'] and tell['payload_fields']
        if case['state'] == 'NOT-EVALUABLE':
            assert case['reason'] == tell['why_not_evaluable']
        else:
            assert len(case['pairs']) == 3 and tell['present_and_absent']
            for pair in case['pairs']:
                assert pair['fake'] != pair['honest'] or pair['fake_files'] != pair['honest_files']


def measure():
    families = {c['family']: dict(caught_and_named=0,total=0,honest_fires=0) for c in CASES}
    failures = []
    with tempfile.TemporaryDirectory(prefix='makoto-tells-') as folder:
        for case,index,pair in PAIRS:
            key = case['id']+'-'+str(index+1)
            fake = run_session(pair, 'fake', Path(folder)/key/'fake')
            honest = run_session(pair, 'honest', Path(folder)/key/'honest')
            caught = bool(fake[-1]) and bool(re.search(r'\b'+case['id']+r'\b', reason(fake[-1]))) and not any(fake[:-1])
            family = families[case['family']]
            family['total'] += 1
            family['caught_and_named'] += int(caught)
            family['honest_fires'] += sum(bool(r) for r in honest)
            if not caught or any(honest):
                failures.append(dict(case=key,fake=fake,honest=honest))
    paths = [ROOT/'REGISTER.md', ROOT/'mesh/TELLS.tsv', ROOT/'tests/fixtures/tells.json', Path(__file__)]
    paths += sorted((ROOT/'plugin/makoto2').glob('*.py'))
    report = dict(families=families,not_evaluable=[dict(id=c['id'],reason=c['reason']) for c in CASES if c['state']=='NOT-EVALUABLE'],
                  failures=failures,source_pins={p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                  reproduction='PYTHONDONTWRITEBYTECODE=1 python3 tests/test_tells.py')
    (ROOT/'mesh/evidence/tells.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(families,indent=2))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(measure())
