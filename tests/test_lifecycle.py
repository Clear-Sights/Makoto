"""Applicable lifecycle regression tests retained from acceptance_tasks.py."""
import csv
from pathlib import Path
import sys
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin"))
HERE = ROOT / "plugin/makoto2"
def table(path):
    with path.open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))

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


def test_validate_current_measurements():
    validate = product_function('validate')
    jobs = {name: {'head': 'selected', 'result': 'pass'}
            for name in ('evaluate', 'observed', 'hook', 'package', 'audit')}
    assert validate('selected', jobs, local_pass=True) == {'decision': 'pass'}
    assert validate('other', jobs, local_pass=True) == {'decision': 'reject'}
    assert validate('selected', jobs, local_pass=False) == {'decision': 'reject'}
    assert validate('selected', {}, local_pass=True) == {'decision': 'reject'}


def test_package_current_bytes_and_fresh_install(tmp_path, monkeypatch):
    import json
    from makoto2 import build_package
    from makoto2.lifecycle import fresh
    artifact = tmp_path / 'artifact'
    result = build_package(ROOT, artifact)
    assert result['version'] == '5.0.0-dev'
    assert result['contents']['makoto2/hook.py'] == (HERE / 'hook.py').read_bytes()
    assert not (artifact / 'makoto2/rows.tsv').exists()
    assert json.loads((artifact / '.claude-plugin/plugin.json').read_text())['version'] == '5.0.0-dev'
    with pytest.raises(FileExistsError):
        build_package(ROOT, artifact)
    with pytest.raises(ValueError):
        build_package(ROOT, ROOT / 'package-output')
    monkeypatch.setenv('MAKOTO_ADAPTER', 'inferred')
    response = fresh(ROOT / 'plugin', tmp_path / 'account', {'session_id': 'fresh', 'hook_event_name': 'Stop', 'last_assistant_message': 'a claim'})
    assert response.get('decision') == 'block'
    assert 'rule a' in response['reason']  # Fresh account has read no artifact.
