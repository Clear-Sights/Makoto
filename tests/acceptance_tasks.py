"""Product acceptance selected by TASKS.tsv; open evidence tasks must fail.
Run individual nodes, not as an unconditional passing regression suite.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugin'))
from makoto2 import hook, evaluate, observed
HERE = ROOT / 'plugin/makoto2'


def table(path):
    return list(csv.DictReader(path.open(), delimiter='\t'))


def suite(*paths):
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *paths], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_decode():
    event = dict(hook_event_name='PreToolUse', session_id='s', tool_name='Read', tool_input={'file_path': '日本語'}, extra=[1, {'a': True}])
    for raw in (json.dumps(event), json.dumps(event).encode()):
        assert hook.d_in(raw) == event
    for raw in ('', '{}', 'null', '[]', '{', '{"hook_event_name":1}', '{"hook_event_name":""}', '{"hook_event_name":"Stop","x":NaN}'):
        assert hook.d_in(raw) is None


def test_configure(monkeypatch, tmp_path):
    monkeypatch.delenv('MAKOTO_STATE_DIR', raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    expected = json.loads((HERE/'config.json').read_text())
    expected['state_dir'] = str(tmp_path/'.claude/makoto2_state')
    assert evaluate.load_cfg(str(HERE/'config.json')) == expected
    assert set(expected) == {line.split('\t')[0] for line in (HERE/'CONFIG_KEYS.txt').read_text().splitlines() if line.strip()}
    monkeypatch.setenv('MAKOTO_STATE_DIR', str(tmp_path/'override'))
    expected['state_dir'] = str(tmp_path/'override')
    assert evaluate.load_cfg(str(HERE/'config.json')) == expected
    bad = tmp_path/'bad.json'; bad.write_text('[]')
    with pytest.raises(ValueError): evaluate.load_cfg(str(bad))


def test_rules(tmp_path):
    rows = evaluate.load_rows(str(HERE/'rows.tsv'), {})
    assert rows and {r['id'] for r in rows} == {r['id'] for r in table(ROOT/'tests/sources.tsv')}
    pins = tmp_path/'pins.tsv'; pins.write_bytes((ROOT/'tests/sources.tsv').read_bytes())
    pins.write_text(pins.read_text().replace('kept asking him', 'wrong quote'))
    with pytest.raises(ValueError): evaluate.load_rows(str(HERE/'rows.tsv'), {}, pins_path=str(pins))
    with pytest.raises(FileNotFoundError): evaluate.load_rows(str(HERE/'rows.tsv'), {}, pins_path=str(tmp_path/'absent'))
    assert not (tmp_path/'absent').exists()
    suite('tests/test_evaluate.py::test_every_row_has_a_case_and_a_verbatim_source')


def test_observe():
    suite('tests/test_observed.py')


def test_evaluate():
    suite('tests/test_evaluate.py')


def test_once():
    finding = dict(row='r1', message='m', objects=['x'])
    rec = observed.record([])
    decision, key = hook.o_once(finding, rec, set())
    assert decision == finding and key
    assert hook.o_once(finding, rec, {key}) == (None, None)
    assert hook.o_once(None, rec, set()) == (None, None)
    changed = observed.record([dict(hook_event_name='PostToolUse', tool_name='Read', tool_input={'file_path':'x'}, tool_response='changed')])
    assert hook.o_once(finding, changed, {key})[0] == finding
    assert hook.o_once(dict(finding, row='r2'), rec, {key})[0]


def test_emit():
    f = dict(row='r', message='m', objects=['x'])
    assert hook.d_out({'hook_event_name':'PreToolUse'}, f)['hookSpecificOutput']['permissionDecision'] == 'deny'
    for event in ('Stop', 'SubagentStop'):
        assert hook.d_out({'hook_event_name':event}, f) == dict(decision='block', reason='makoto r: m')
    for event in ('Stop', 'PreToolUse', 'PostToolUse', 'FutureEvent'):
        assert hook.d_out({'hook_event_name':event}, None) == {}
    assert hook.d_out({'hook_event_name':'FutureEvent'}, f) == {}


def test_advance(tmp_path):
    cfg = dict(state_dir=str(tmp_path/'state'))
    records = []
    def rec(events):
        records.append(events); return observed.record(events)
    def finding(rows, record, event):
        assert not record.obs
        return None
    def run(name):
        ev = dict(hook_event_name=name, session_id='s', tool_name='Read', tool_input={'file_path':'x'}, tool_response='text')
        return hook.main(json.dumps(ev), cfg, [], rec, finding)
    assert run('PreToolUse') == {} and records[-1] == []
    assert run('PostToolUse') == {} and len(records[-1]) == 1
    for name in ('UserPromptSubmit', 'SubagentStop', 'Stop'):
        assert hook.main(json.dumps(dict(hook_event_name=name, session_id='s')), cfg, [], rec, lambda *a: None) == {}
        assert records[-1][-1]['hook_event_name'] != name
    events, _ = hook.sigma_read(hook.sigma_path(cfg['state_dir'], 's'))
    assert [e['hook_event_name'] for e in events] == ['PostToolUse','UserPromptSubmit','SubagentStop','Stop']


def test_persist(tmp_path):
    path = hook.sigma_path(str(tmp_path/'state'), 's')
    other = hook.sigma_path(str(tmp_path/'state'), '../other')
    assert path != other and Path(other).parent == Path(path).parent
    assert hook.sigma_read(path) == ([], set()) and not Path(path).exists()
    event = dict(hook_event_name='PostToolUse', session_id='s')
    hook.sigma_append(path, {'event':event})
    before = Path(path).read_bytes()
    hook.sigma_append(path, {'key':'k'})
    assert Path(path).read_bytes().startswith(before)
    assert hook.sigma_read(path) == ([event], {'k'})
    assert hook.sigma_read(other) == ([], set())
    with pytest.raises(ValueError): hook.sigma_append(path, {'x':float('nan')})
    with pytest.MonkeyPatch.context() as patch:
        test_configure(patch, tmp_path)


def require_receipt(task):
    receipt = json.loads((ROOT/f'mesh/evidence/{task}.json').read_text())
    assert receipt.get('task') == task
    assert receipt.get('result') == 'pass' and not receipt.get('absent') and not receipt.get('external'), f'{task}: current product evidence absent or external'
    pins = receipt.get('source_pins', {})
    assert pins
    # A receipt must bind product inputs, not just a convenient mesh fixture.
    mandatory = {str(p.relative_to(ROOT)) for p in HERE.iterdir() if p.is_file()}
    assert mandatory <= pins.keys(), 'receipt does not bind shipped product'
    for name, digest in pins.items():
        path = ROOT/name
        assert path.resolve().is_relative_to(ROOT) and path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, f'stale input: {name}'
    canonical = json.dumps(pins, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    assert hashlib.sha256(canonical).hexdigest() == receipt.get('selected_input_digest')
    observations = receipt.get('observations')
    assert observations and all(o.get('result') == 'pass' for o in observations)
    assert any(o.get('synthetic') is not True for o in observations)
    slot = next(s for s in table(ROOT/'mesh/SLOTS.tsv') if s['slot'] == task)
    assert slot['filled-by'], 'missing proof producer'
    requirements = set(slot['requirements'].split(','))
    assert requirements <= set(receipt.get('requirements', [])), 'receipt omits requirements'
    present = set(receipt.get('present', []))
    for requirement in table(ROOT/'mesh/REQUIREMENTS.tsv'):
        if requirement['requirement'] in requirements:
            for relation in json.loads(requirement['required']):
                assert relation in present or requirement['requirement']+':'+relation in present, 'unproven required case: '+relation
    for binding in slot['filled-by'].split(';'):
        name, unit = binding.split(':', 1)
        assert (ROOT/name).is_file(), 'missing proof producer file'
        if unit != '<module>':
            sys.path.insert(0, str(ROOT/'mesh'))
            from check import units
            assert unit in units(ROOT/name), 'missing proof producer unit'
    return receipt


def test_register(): require_receipt('register')
def test_validate():
    suite('tests/test_evaluate.py', 'tests/test_observed.py', 'tests/test_hook.py')
    require_receipt('validate')
def test_package(): require_receipt('package')
def test_fresh(): require_receipt('fresh')
def test_audit(): require_receipt('audit')
def test_join():
    for task in ('register','validate','package','fresh','audit'): require_receipt(task)
    assert require_receipt('join').get('decision') == 'done'
def test_handoff(): require_receipt('handoff')


def test_subtract():
    sys.path.insert(0, str(ROOT/'mesh'))
    from check import old_unit_present
    for row in table(ROOT/'mesh/SUBTRACT.tsv'):
        current = ROOT/row['path']; reference = ROOT/'mesh/reference'/current.name
        assert reference.is_file()
        assert not current.exists() or not old_unit_present(current, reference, row['unit'])


def test_zero():
    # Successful report generation is not implementation completion.
    for task in ('register','validate','package','fresh','audit','join','handoff'): require_receipt(task)
    receipt = json.loads((ROOT/'mesh/evidence/zero.json').read_text())
    assert receipt.get('done') is True and receipt.get('decision') == 'done'
    assert not receipt.get('absent') and not receipt.get('external')
    sys.path.insert(0, str(ROOT/'mesh'))
    from zero import measure, sha
    files, missing = measure(ROOT)
    assert not missing and receipt.get('source_pins') == {n:sha(b) for n,b in files.items()}
