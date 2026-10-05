"""Product acceptance selected by TASKS.tsv; open evidence tasks must fail.
Run individual nodes, not as an unconditional passing regression suite.
"""
import csv
import json
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


def product_function(name):
    """Open lifecycle slots must expose executable behavior, never a proof file."""
    import importlib.util
    path = HERE / 'lifecycle.py'
    assert path.is_file(), f'{name}: missing product implementation plugin/makoto2/lifecycle.py'
    spec = importlib.util.spec_from_file_location('makoto_lifecycle_acceptance', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, name, None)
    assert callable(fn), f'{name}: missing executable product function'
    return fn


def test_register():
    # Replay the CURRENT shipped register. Amendments are solely owner proposals.
    rows = evaluate.load_rows(str(HERE/'rows.tsv'), {})
    assert [r['id'] for r in rows] == ['R01', 'R03', 'R04', 'R05', 'R06', 'R07',
                                     'R08', 'R09', 'R10', 'R11', 'R12', 'R13', 'R14']
    suite('tests/test_evaluate.py', 'tests/test_goal.py')


def test_validate():
    suite('tests/test_evaluate.py', 'tests/test_observed.py', 'tests/test_hook.py')
    validate = product_function('validate')
    jobs = {name: {'head': 'selected', 'result': 'pass'}
            for name in ('evaluate', 'observed', 'hook', 'package', 'audit')}
    assert validate('selected', jobs, local_pass=True) == {'decision': 'pass'}
    assert validate('other', jobs, local_pass=True) == {'decision': 'reject'}
    assert validate('selected', jobs, local_pass=False) == {'decision': 'reject'}
    assert validate('selected', {}, local_pass=True) == {'decision': 'reject'}


def test_package(tmp_path):
    package = product_function('package')
    result = package(ROOT, tmp_path/'artifact')
    assert result['version'] == '4.0.1'
    artifact = Path(result['path'])
    assert artifact.is_dir()
    assert (artifact/'makoto2/rows.tsv').read_bytes() == (HERE/'rows.tsv').read_bytes()
    assert (artifact/'makoto2/__main__.py').is_file()
    assert json.loads((artifact/'.claude-plugin/plugin.json').read_text())['version'] == '4.0.1'
    assert (artifact/'UNINSTALL.md').is_file()
    assert not (artifact/'mesh/evidence').exists()
    assert result['contents']['makoto2/rows.tsv'] == (HERE/'rows.tsv').read_bytes()
    assert result['input_digest']
    with pytest.raises(FileExistsError):
        package(ROOT, artifact)
    assert (artifact/'makoto2/rows.tsv').read_bytes() == (HERE/'rows.tsv').read_bytes()
    with pytest.raises(ValueError):
        package(ROOT, ROOT/'package-output')
    # Measure new source bytes directly; no retained evidence is required.
    source = tmp_path/'source'
    runtime = source/'plugin/makoto2'
    runtime.mkdir(parents=True)
    (runtime/'__main__.py').write_text('print("first")\n')
    (runtime/'rows.tsv').write_text('current rules\n')
    (runtime/'__pycache__').mkdir()
    (runtime/'__pycache__/cached.pyc').write_bytes(b'stale cache')
    first = package(source, tmp_path/'first')
    repeat = package(source, tmp_path/'repeat')
    assert first['contents'] == repeat['contents']
    assert first['input_digest'] == repeat['input_digest']
    assert 'makoto2/__pycache__/cached.pyc' not in first['contents']
    (runtime/'rows.tsv').write_text('changed rules\n')
    changed = package(source, tmp_path/'changed')
    assert changed['contents']['makoto2/rows.tsv'] == b'changed rules\n'
    assert changed['input_digest'] != first['input_digest']
    with pytest.raises(FileNotFoundError):
        package(tmp_path/'missing-source', tmp_path/'missing-artifact')
    assert not (tmp_path/'missing-artifact').exists()
    suite('tests/test_hook.py')


def test_fresh(tmp_path):
    fresh = product_function('fresh')
    slip = {'hook_event_name': 'Stop', 'session_id': 'new',
            'last_assistant_message': 'Want me to push this?'}
    control = dict(slip, last_assistant_message='Pushing next; that is the default.')
    assert fresh(ROOT/'plugin', tmp_path/'account', slip)['decision'] == 'block'
    assert fresh(ROOT/'plugin', tmp_path/'other-account', control) == {}
    with pytest.raises(FileNotFoundError):
        fresh(tmp_path/'missing-plugin', tmp_path/'missing-account', slip)


def test_audit(tmp_path):
    audit = product_function('audit')
    (tmp_path/'source.py').write_text('value = 1\n')
    assert audit(tmp_path)['decision'] == 'clean'
    # Include ignored content, and exclude history.
    (tmp_path/'.git').mkdir()
    (tmp_path/'.git/history').write_text('AKIA' + 'A'*16)
    assert audit(tmp_path)['decision'] == 'clean'
    (tmp_path/'.gitignore').write_text('ignored.txt\n')
    (tmp_path/'ignored.txt').write_text('AKIA' + 'A'*16)
    rejected = audit(tmp_path)
    assert rejected['decision'] == 'reject'
    # A retained passing receipt cannot override current credential bytes.
    (tmp_path/'evidence.json').write_text('{"decision":"clean","result":"pass"}')
    assert audit(tmp_path)['decision'] == 'reject'
    (tmp_path/'ignored.txt').write_text('safe current content\n')
    clean = audit(tmp_path)
    assert clean['decision'] == 'clean'
    assert clean['input_digest'] != rejected['input_digest']
    assert audit(tmp_path) == clean
    hidden = tmp_path/'.hidden'
    hidden.mkdir()
    (hidden/'binary').write_bytes(b'\x00\xff' + b'ASIA' + b'B'*16)
    assert audit(tmp_path)['decision'] == 'reject'
    (hidden/'binary').unlink()
    (hidden/'key').write_text('-----BEGIN ' + 'PRIVATE KEY-----\n')
    assert audit(tmp_path)['decision'] == 'reject'
    (hidden/'key').unlink()
    (hidden/'link').symlink_to(tmp_path/'source.py')
    assert audit(tmp_path)['decision'] == 'reject'
    with pytest.raises(FileNotFoundError):
        audit(tmp_path/'missing')


def test_join():
    join = product_function('join')
    inputs = {name: {'head': 'selected', 'decision': 'pass'}
              for name in ('register', 'validate', 'package', 'fresh', 'audit')}
    assert join('selected', inputs) == {'decision': 'done'}
    assert join('other', inputs) == {'decision': 'not_done'}
    for name in inputs:
        assert join('selected', {k: v for k, v in inputs.items() if k != name}) == {'decision': 'not_done'}


def test_handoff():
    handoff = product_function('handoff')
    selected = {'project': 'makoto', 'head': 'selected', 'decision': 'not_done',
                'absent': ['fresh']}
    expected = {'project': 'makoto', 'head': 'selected', 'decision': 'not_done',
                'absent': ['fresh'], 'wake': 'changed_input'}
    assert handoff(selected) == expected
    assert handoff(dict(selected)) == expected
    assert handoff(dict(selected, head='changed'))['head'] == 'changed'


def test_subtract():
    sys.path.insert(0, str(ROOT/'mesh'))
    from check import old_unit_present
    for row in table(ROOT/'mesh/SUBTRACT.tsv'):
        current = ROOT/row['path']; reference = ROOT/'mesh/reference'/current.name
        assert reference.is_file()
        assert not current.exists() or not old_unit_present(current, reference, row['unit'])


def test_zero():
    # Execute every completion obligation; handwritten receipts cannot close zero.
    suite(
        'tests/acceptance_tasks.py::test_decode',
        'tests/acceptance_tasks.py::test_configure',
        'tests/acceptance_tasks.py::test_rules',
        'tests/acceptance_tasks.py::test_observe',
        'tests/acceptance_tasks.py::test_evaluate',
        'tests/acceptance_tasks.py::test_once',
        'tests/acceptance_tasks.py::test_emit',
        'tests/acceptance_tasks.py::test_advance',
        'tests/acceptance_tasks.py::test_persist',
        'tests/acceptance_tasks.py::test_register',
        'tests/acceptance_tasks.py::test_validate',
        'tests/acceptance_tasks.py::test_package',
        'tests/acceptance_tasks.py::test_fresh',
        'tests/acceptance_tasks.py::test_audit',
        'tests/acceptance_tasks.py::test_join',
        'tests/acceptance_tasks.py::test_handoff',
        'tests/acceptance_tasks.py::test_subtract',
    )
