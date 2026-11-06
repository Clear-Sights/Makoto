"""Rule f, Openness: Downstream. A changed definition owes the session a reading of every file that uses its name."""
import subprocess

import pytest

from test_rules import send, stop

A = 'def area(w, h):\n    return w * h\n\nLIMIT = 10\n'
A_EDIT = {'old_string': 'def area(w, h):', 'new_string': 'def area(w, h, unit):'}
B = 'from a import area\nprint(area(2, 3))\n'
C = 'import a\nx = a.area(4, 5)\n'


def tree(tmp_path, **files):
    root = tmp_path / 'repo'
    root.mkdir()
    for name, text in files.items():
        (root / name).write_text(text)
    return root


def ev(root, name, **fields):
    return dict(hook_event_name=name, session_id='down', cwd=str(root), **fields)


def call(root, tool, tool_input, response, tid):
    return [ev(root, 'PreToolUse', tool_name=tool, tool_use_id=tid, tool_input=tool_input),
            ev(root, 'PostToolUse', tool_name=tool, tool_use_id=tid, tool_input=tool_input, tool_response=response)]


def read(root, name, text, tid=None):
    path = str(root / name)
    return call(root, 'Read', {'file_path': path}, {'type': 'text', 'file': {'filePath': path, 'content': text}}, tid or 'read-' + name)


def edit(root, name='a.py', change=A_EDIT, tid='edit'):
    return call(root, 'Edit', dict(change, file_path=str(root / name)), {'content': 'ok'}, tid)


def run(root, name='a.py', tid='run'):
    return call(root, 'Bash', {'command': 'python3 ' + name}, {'stdout': '6\n', 'exitCode': 0}, tid)


def finish(root, **extra):
    # A fresh reading of something that is not a use of the name, then the Stop under test.
    return read(root, 'notes.txt', 'spec', 'notes') + [dict(stop('Done'), session_id='down', cwd=str(root), **extra)]


def play(tmp_path, root, events):
    for event in events[:-1]:
        assert send(tmp_path, event) == {}
    return send(tmp_path, events[-1])


def reason(response):
    return response.get('reason') or response.get('hookSpecificOutput', {}).get('permissionDecisionReason', '')


def opening(root):
    return read(root, 'a.py', A)


def test_a_changed_definition_with_an_unread_use_is_held_and_named(tmp_path):
    root = tree(tmp_path, **{'a.py': A, 'b.py': B})
    held = play(tmp_path, root, opening(root) + edit(root) + run(root) + finish(root))
    text = reason(held)
    assert held.get('decision') == 'block' or held.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'
    assert text.startswith('makoto rule f [downstream]: "area": ')
    assert 'Openness: Downstream' in text and 'b.py:1' in text and 'b.py:2' in text
    assert text.endswith('Clear: Read b.py.')


def test_reading_the_named_file_clears_the_hold(tmp_path):
    root = tree(tmp_path, **{'a.py': A, 'b.py': B})
    events = opening(root) + edit(root) + run(root) + read(root, 'b.py', B)
    assert play(tmp_path, root, events + finish(root)) == {}


def test_every_unread_file_is_listed_and_each_must_be_read(tmp_path):
    root = tree(tmp_path, **{'a.py': A, 'b.py': B, 'c.py': C})
    held = play(tmp_path, root, opening(root) + edit(root) + run(root) + read(root, 'b.py', B) + finish(root))
    listed = reason(held).split('Missing:')[1]
    assert reason(held).endswith('Clear: Read c.py.') and 'c.py:2' in listed and 'b.py' not in listed
    assert play(tmp_path, root, read(root, 'c.py', C) + finish(root)[1:]) == {}


def test_a_name_with_no_use_elsewhere_holds_nothing(tmp_path):
    root = tree(tmp_path, **{'a.py': A, 'b.py': 'print(1)\n'})
    assert play(tmp_path, root, opening(root) + edit(root) + run(root) + finish(root)) == {}


def test_a_use_in_a_file_the_session_changed_is_accounted_for(tmp_path):
    root = tree(tmp_path, **{'a.py': A, 'b.py': B})
    fix = {'old_string': 'area(2, 3)', 'new_string': "area(2, 3, 'cm')"}
    events = read(root, 'b.py', B) + opening(root) + edit(root) + run(root) + edit(root, 'b.py', fix, 'fix') + run(root, 'b.py', 'run-b')
    assert play(tmp_path, root, events + finish(root)) == {}


def test_a_reading_made_before_the_change_does_not_count(tmp_path):
    root = tree(tmp_path, **{'a.py': A, 'b.py': B})
    events = read(root, 'b.py', B) + opening(root) + edit(root) + run(root)
    assert 'Clear: Read b.py.' in reason(play(tmp_path, root, events + finish(root)))


def test_the_definition_line_unchanged_holds_nothing(tmp_path):
    root = tree(tmp_path, **{'a.py': A, 'b.py': B})
    body = {'old_string': 'return w * h', 'new_string': 'return h * w'}
    assert play(tmp_path, root, opening(root) + edit(root, change=body) + run(root) + finish(root)) == {}


def test_a_module_level_assignment_counts_but_a_local_one_does_not(tmp_path):
    root = tree(tmp_path, **{'a.py': A + 'def f():\n    n = 1\n    return n\n', 'b.py': 'from a import LIMIT\nn = 2\nprint(LIMIT)\n'})
    text = A + 'def f():\n    n = 1\n    return n\n'
    local = {'old_string': '    n = 1', 'new_string': '    n = 2'}
    assert play(tmp_path / 'local', root, read(root, 'a.py', text) + edit(root, change=local) + run(root) + finish(root)) == {}
    module = {'old_string': 'LIMIT = 10', 'new_string': 'LIMIT = 20'}
    held = play(tmp_path / 'module', root, read(root, 'a.py', text) + edit(root, change=module) + run(root) + finish(root))
    assert reason(held).startswith('makoto rule f [downstream]: "LIMIT": ')


def test_a_write_over_a_read_file_that_drops_a_definition_is_held(tmp_path):
    root = tree(tmp_path, **{'a.py': A, 'b.py': B})
    rewrite = call(root, 'Write', {'file_path': str(root / 'a.py'), 'content': 'def area3(w, h, d):\n    return w * h * d\n\nLIMIT = 10\n'}, {'content': 'ok'}, 'rewrite')
    assert 'Clear: Read b.py.' in reason(play(tmp_path, root, opening(root) + rewrite + run(root) + finish(root)))


def test_a_multiedit_is_read_on_each_of_its_edits(tmp_path):
    root = tree(tmp_path, **{'a.py': A, 'b.py': B})
    multi = call(root, 'MultiEdit', {'file_path': str(root / 'a.py'), 'edits': [A_EDIT, {'old_string': 'LIMIT = 10', 'new_string': 'LIMIT = 11'}]}, {'content': 'ok'}, 'multi')
    assert 'Clear: Read b.py.' in reason(play(tmp_path, root, opening(root) + multi + run(root) + finish(root)))


def test_git_commit_and_push_are_held_too(tmp_path):
    root = tree(tmp_path, **{'a.py': A, 'b.py': B})
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    commit = ev(root, 'PreToolUse', tool_name='Bash', tool_use_id='ship', tool_input={'command': 'git commit -am "area takes a unit"'})
    held = play(tmp_path, root, opening(root) + edit(root) + run(root) + [commit])
    assert 'makoto rule f [downstream]: "area"' in reason(held)
    assert reason(held).endswith('Clear: Read b.py.')


def test_git_grep_sees_an_untracked_use_and_ignores_the_changed_file(tmp_path):
    root = tree(tmp_path, **{'a.py': A, 'b.py': B})
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    held = play(tmp_path, root, opening(root) + edit(root) + run(root) + finish(root))
    assert 'a.py' not in reason(held).split('Missing:')[1] and 'b.py:2' in reason(held)


def test_a_recorded_downstream_replaces_the_scan(tmp_path):
    root = tree(tmp_path, **{'a.py': A})
    ending = finish(root, makoto={'downstream': [{'name': 'area', 'path': 'z.py', 'line': 7}]})
    held = play(tmp_path, root, opening(root) + edit(root) + run(root) + ending)
    assert 'z.py:7' in reason(held) and reason(held).endswith('Clear: Read z.py.')


def test_user_prompts_are_never_blocked(tmp_path):
    root = tree(tmp_path, **{'a.py': A, 'b.py': B})
    for event in opening(root) + edit(root):
        send(tmp_path, event)
    assert send(tmp_path, ev(root, 'UserPromptSubmit', prompt='go on')) == {}
