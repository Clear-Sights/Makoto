"""Windows record plants that also run on a POSIX host."""
import ntpath
import os
from pathlib import PureWindowsPath
from types import SimpleNamespace

import pytest

from test_shapes import output, pair
from test_switch import edit, feed, switch_holds
from test_questions import bash_executable
import makoto2
from makoto2 import evaluate as evaluation, observed, switch
from makoto2.provenance import Ledger


@pytest.fixture
def windows_paths(monkeypatch):
    # Patch only the product modules, leaving pytest's real filesystem alone.
    windows = SimpleNamespace(path=ntpath, sep='\\', getcwd=lambda: 'D:\\work',
                              access=os.access, X_OK=os.X_OK)
    for module in (observed, evaluation, switch):
        monkeypatch.setattr(module, 'os', windows)


def test_package_keys_use_slashes_with_windows_relative_paths(tmp_path, monkeypatch):
    path_type = type(tmp_path)
    relative_to = path_type.relative_to
    with monkeypatch.context() as patch:
        patch.setattr(path_type, 'relative_to',
                      lambda path, *args, **kwargs: PureWindowsPath(
                          *relative_to(path, *args, **kwargs).parts))
        result = makoto2.build_package(makoto2.Path(__file__).resolve().parents[1],
                                      tmp_path / 'package')
    assert result['contents']['makoto2/hook.py']
    assert all('\\' not in key for key in result['contents'])


@pytest.mark.parametrize('path,cwd,expected', [
    ('loom.py', '/w', 'file:/w/loom.py'),
    ('pkg\\loom.py', '/w', 'file:/w/pkg/loom.py'),
    ('C:\\work\\pkg\\..\\loom.py', 'D:\\work', 'file:C:/work/loom.py'),
    ('pkg/loom.py', 'C:\\work', 'file:C:/work/pkg/loom.py'),
    ('\\\\server\\share\\loom.py', 'D:\\work', 'file://server/share/loom.py'),
])
def test_record_identity_accepts_either_separator(windows_paths, path, cwd, expected):
    assert observed.identity(path, {'cwd': cwd}) == expected


def test_mixed_separators_invalidate_readings_but_not_exact_name_bytes(windows_paths):
    ledger = Ledger()
    feed(ledger, pair(ti={'file_path': 'C:/work/source.txt'}))
    assert ledger.witnesses('C:/work/source.txt', 'path')
    assert not ledger.witnesses('C:\\work\\source.txt', 'path')
    feed(ledger, edit('C:\\work\\source.txt'))
    assert not ledger.source_readings()
    assert not ledger.witnesses('C:/work/source.txt', 'path')


def test_mixed_separator_edit_and_module_run(windows_paths):
    ledger = Ledger()
    change = edit('C:\\work\\pkg\\branch.py')
    for ev in change:
        ev['cwd'] = 'C:\\work'
    feed(ledger, change)
    assert switch_holds(ledger)
    assert 'pkg.branch' in next(iter(ledger.changed_code().values()))['aliases']
    call = pair('Bash', {'command': 'python.exe -m pkg.branch'}, 'response', tid='run')
    for ev in call:
        ev['cwd'] = 'C:/work'
    feed(ledger, call)
    assert not switch_holds(ledger)


@pytest.mark.parametrize('reference', ['/w/my report.txt', '\\w\\my report.txt'])
def test_spaced_output_keeps_recorded_separator_exemption(windows_paths, reference):
    ledger = Ledger()
    feed(ledger, pair())
    change = edit('my report.txt')
    for ev in change:
        ev['tool_input']['content'] = 'source data'
    feed(ledger, change)
    findings, _ = evaluation.evaluate(ledger, output(reference))
    assert not findings
    findings, _ = evaluation.evaluate(ledger, output(reference + 'Extra'))
    assert any(f['rule'] == 'b' for f in findings)


def test_windows_python_executable_failed_response_pays(windows_paths):
    ledger = Ledger()
    change = edit('branch.py')
    for ev in change:
        ev['cwd'] = 'C:\\work'
    feed(ledger, change)
    candidate = dict(output('Done'), cwd='C:\\work')
    assert switch_holds(ledger, candidate)
    call = pair('Bash', {'command': '"C:/Program Files/Python/python.exe" branch.py'},
                'RuntimeError: response', tid='run')
    for ev in call:
        ev['cwd'] = 'C:\\work'
    call[1]['hook_event_name'] = 'PostToolUseFailure'
    call[1]['tool_response']['exitCode'] = 1
    feed(ledger, call)
    assert not switch_holds(ledger, candidate)


@pytest.mark.parametrize('command', [
    '"C:/Python/python.exe" -c "print(1)" branch.py',
    '"C:/Python/python.exe" --help branch.py',
    '"C:/Python/python.exe" other.py branch.py',
])
def test_windows_interpreter_near_misses_do_not_pay(windows_paths, command):
    ledger = Ledger()
    feed(ledger, edit())
    feed(ledger, pair('Bash', {'command': command}, 'response', tid='run'))
    assert switch_holds(ledger)


def test_windows_bash_fixture_chooses_git_bash(monkeypatch):
    import test_questions
    monkeypatch.setattr(test_questions.sys, 'platform', 'win32')
    monkeypatch.setenv('ProgramFiles', 'C:/Program Files')
    monkeypatch.setattr(test_questions.Path, 'is_file', lambda path: path.as_posix() ==
                        'C:/Program Files/Git/bin/bash.exe')
    assert str(bash_executable.__wrapped__()).replace('\\', '/') == \
        'C:/Program Files/Git/bin/bash.exe'


def test_cross_drive_edit_and_writer_reference_need_no_relpath(windows_paths, monkeypatch):
    def same_drive_relpath(path, start):
        # A cross-drive relpath must never be attempted, even inside a try.
        assert ntpath.splitdrive(path)[0].lower() == ntpath.splitdrive(start)[0].lower()
        return original_relpath(path, start)

    original_relpath = ntpath.relpath
    monkeypatch.setattr(ntpath, 'relpath', same_drive_relpath)
    monkeypatch.setattr(ntpath, 'isfile', lambda path: path == 'C:/bin/worker')
    monkeypatch.setattr(switch.os, 'access', lambda path, mode: True)
    ledger = Ledger()
    change = edit('C:/bin/worker')
    for ev in change:
        ev['cwd'] = 'D:\\work'
    feed(ledger, change)
    candidate = dict(output('C:/bin/worker', 'Write'), cwd='D:\\work')
    assert switch_holds(ledger, candidate)
    unrelated = dict(output('unrelated text', 'Write'), cwd='D:\\work')
    assert not switch_holds(ledger, unrelated)
    feed(ledger, pair('Run', {'file_path': 'C:/bin/worker'}, 'response', tid='run'))
    assert not switch_holds(ledger, candidate)


def test_cross_drive_spaced_output_exemption(windows_paths):
    ledger = Ledger()
    feed(ledger, pair())
    change = edit('C:/reports/my report.txt')
    for ev in change:
        ev['tool_input']['content'] = 'source data'
    feed(ledger, change)
    candidate = dict(output('C:/reports/my report.txt'), cwd='D:\\work')
    findings, _ = evaluation.evaluate(ledger, candidate)
    assert not findings
