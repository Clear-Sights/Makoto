"""Windows payloads use Windows identities even when evaluated on Linux."""
import builtins
import copy
import importlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin'))
from makoto2 import observed as reader

CASES = json.loads((Path(__file__).parent / 'fixtures/goal.json').read_text())
IDS = {'A2', 'D4', 'D11', 'F7', 'G1', 'F10', 'H1', 'H2', 'H4', 'H5', 'C7', 'D1', 'H6'}


@pytest.mark.parametrize('cwd', [r'C:\Users\RunnerAdmin\Temp\Fake', 'c:/USERS/runneradmin/TEMP/fake'])
@pytest.mark.parametrize('case', [c for c in CASES if c['id'] in IDS], ids=lambda c: c['id'])
def test_windows_fake_and_honest(case, cwd, tmp_path, monkeypatch):
    # A small filesystem adapter supplies real harness files under a Windows root.
    # It deliberately does not normalize identities: consumers must pass absolute paths.
    root = 'c:/users/runneradmin/temp/fake/'
    original_open, original_exists, original_isfile = builtins.open, reader.os.path.exists, reader.os.path.isfile

    def local(path):
        spelling = str(path).replace('\\', '/').lower()
        return tmp_path / spelling[len(root):] if spelling.startswith(root) else path

    monkeypatch.setattr(builtins, 'open', lambda path, *a, **kw: original_open(local(path), *a, **kw))
    monkeypatch.setattr(reader.os.path, 'exists', lambda path: original_exists(local(path)))
    monkeypatch.setattr(reader.os.path, 'isfile', lambda path: original_isfile(local(path)))
    module, name = case['predicate'].split('.')
    predicate = getattr(importlib.import_module('makoto2.' + module), name)
    for side in ('fake', 'honest'):
        for old in tmp_path.rglob('*'):
            if old.is_file():
                old.unlink()
        for path, content in dict(case.get('files', {}), **case.get(side + '_files', {})).items():
            target = tmp_path / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        events = copy.deepcopy(case[side])
        for event in events:
            event['cwd'] = cwd
        # Mix absolute, case-varied reads with relative current dependencies/claims.
        for event in events[:-1]:
            ti = event.get('tool_input', {})
            if 'file_path' in ti:
                ti['file_path'] = cwd.upper() + '\\' + ti['file_path'].upper().replace('/', '\\')
        result = predicate(reader.record(events[:-1]), events[-1], reader)
        assert bool(result) == (side == 'fake'), (case['id'], side, result)


@pytest.mark.parametrize('path', [r'C:\REPO\Output\..\Source.py:12:3', 'c:/repo/source.py', r'.\SOURCE.py'])
def test_windows_record_identity(path):
    history = [dict(hook_event_name='PostToolUse', tool_name='Read', cwd=r'C:\Repo',
                    tool_input={'file_path': path}, tool_response='value')]
    rec = reader.record(history)
    current = dict(tool_name='Edit', cwd='c:/REPO', tool_input={'file_path': 'source.py'})
    assert rec.observed(rec.objects_of(current))
    assert reader._text_objects(r'Source C:\REPO\Source.py', '') == {'c:/repo/source.py'}
    assert not rec.observed({'c:/repo/other.py'})
    assert reader._text_objects(r'Source C:\Source.py', '') == {'c:/source.py'}
    assert reader._text_objects(r'Source \\SERVER\Share\Source.py', '') == {'//server/share/source.py'}


def test_posix_case_urls_and_counts_remain_distinct():
    assert reader._norm('Source.py', '/Repo') == '/Repo/Source.py'
    assert reader._norm('https://Example.com/Source.py', r'C:\Repo') == 'https://Example.com/Source.py'
    assert reader._norm('8/8', r'C:\Repo') == '8/8'


class WindowsPath:
    """Real temporary bytes with a Windows spelling, regardless of test host."""
    def __init__(self, local, spelling=r'C:\Users\RunnerAdmin\Temp\Case'):
        self.local, self.spelling = local, spelling

    def __str__(self):
        return self.spelling

    def __truediv__(self, name):
        return WindowsPath(self.local / name, self.spelling + '\\' + name)

    def mkdir(self):
        self.local.mkdir()

    def write_text(self, text):
        return self.local.write_text(text)

    def unlink(self):
        self.local.unlink()


@pytest.fixture
def windows_tmp(tmp_path, monkeypatch):
    root = WindowsPath(tmp_path)
    original_open, original_exists = builtins.open, reader.os.path.exists
    prefix = reader._norm(str(root), '') + '/'

    def local(path):
        spelling = str(path)
        return tmp_path / spelling[len(prefix):] if spelling.startswith(prefix) else path

    monkeypatch.setattr(reader.os.path, 'exists', lambda path: original_exists(local(path)))
    monkeypatch.setattr(builtins, 'open', lambda path, *a, **kw: original_open(local(path), *a, **kw))
    return root


def test_windows_slash_words_need_path_evidence(windows_tmp):
    from test_observed import test_slash_words_need_path_evidence
    test_slash_words_need_path_evidence(windows_tmp)


def test_windows_preserving_whole_write_must_keep_unrelated_lines(windows_tmp):
    from test_restored_fixes import test_preserving_whole_write_must_keep_unrelated_lines
    test_preserving_whole_write_must_keep_unrelated_lines(windows_tmp)


def test_windows_asserted_sources_require_direct_reading(windows_tmp):
    from test_restored_fixes import test_asserted_sources_require_direct_reading
    test_asserted_sources_require_direct_reading(windows_tmp)


@pytest.mark.parametrize('path', [r'C:\Users\RunnerAdmin\policy.txt',
                                  r'notes\policy.txt', r'.\notes\policy.txt',
                                  r'\\server\share\policy.txt'])
@pytest.mark.parametrize('quote', ['', '"', "'"])
def test_windows_shell_path_arguments(path, quote):
    assert reader._segments('cat ' + quote + path + quote) == ((('cat', path), ''),)


def test_posix_shell_escapes():
    assert reader._segments(r'cat some\ file.txt; echo \$HOME \"') == (
        (('cat', 'some file.txt'), ';'), (('echo', '$HOME', '"'), ''))
