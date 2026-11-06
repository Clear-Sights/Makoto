"""Regression tests: each one failed on the code before its fix."""
import sys

import pytest

from test_rules import PLUGIN

sys.path.insert(0, str(PLUGIN))
import makoto2 as m  # noqa: E402


def bash(command, **extra):
    return dict({'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'tool_use_id': 't',
                 'session_id': 's', 'cwd': '/r', 'tool_input': {'command': command}}, **extra)


def shipped(command, staged, changes):
    ledger = m.Ledger()
    ledger.staged_code = dict(staged)
    return m.commit_changes(ledger, bash(command), changes)


CHANGES = {'file:/r/src/a.py': 1, 'file:/r/README.md': 2}


def test_redirect_keeps_a_bare_digit_argument():
    assert m.redirected_argv('echo 2 > out.txt') == (('echo', '2'), (('>', 'out.txt'),))
    assert m.redirected_argv('ls 2>err.txt') == (('ls',), (('>', 'err.txt'),))


def test_url_keeps_balanced_closing_paren():
    urls = [s.text for s in m.extract('see https://en.wikipedia.org/wiki/Python_(programming_language)') if s.kind == 'url']
    assert urls == ['https://en.wikipedia.org/wiki/Python_(programming_language)']
    urls = [s.text for s in m.extract('(see https://example.com/a)') if s.kind == 'url']
    assert urls == ['https://example.com/a']


def test_mv_with_several_sources_removes_each():
    effects = m.effects(bash('mv a.txt b.txt dest/'))
    assert {e['subject'] for e in effects if e.get('removed')} == {'a.txt', 'b.txt'}


def test_git_add_all_with_a_pathspec_stages_only_that_path():
    assert shipped('git add -A src/a.py && git commit -m x', {}, CHANGES) == {'file:/r/src/a.py': 1}
    assert shipped('git add -A && git commit -m x', {}, CHANGES) == CHANGES


def test_git_reset_to_a_revision_unstages_everything():
    staged = {'file:/r/src/a.py': 1}
    assert shipped('git reset HEAD && git commit -m x', staged, {}) == {}
    assert shipped('git reset -- src/a.py && git commit -m x', staged, {}) == {}


def test_status_decodes_octal_quoted_paths():
    pre = bash('git status --porcelain')
    post = dict(pre, hook_event_name='PostToolUse', tool_response={'stdout': ' M "caf\\303\\251.py"\n', 'exit_code': 0})
    ledger = m.Ledger()
    m.record_git(ledger, pre, post)
    assert ledger.git_tracked == {'file:/r/café.py'}


def test_deeply_nested_json_payload_does_not_raise():
    event = {'hook_event_name': 'PreToolUse', 'tool_name': 'Write', 'cwd': '/tmp', 'session_id': 's',
             'tool_input': {'file_path': '/tmp/x.txt', 'content': '[' * 100000 + ']' * 100000}}
    m.edited_forms(event, 'file:/tmp/x.txt')
