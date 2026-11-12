"""Regression tests: each one failed on the code before its fix."""
import sys

from test_rules import PLUGIN

sys.path.insert(0, str(PLUGIN))
import makoto2 as m  # noqa: E402


def bash(command, **extra):
    return dict({'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'tool_use_id': 't',
                 'session_id': 's', 'cwd': '/r', 'tool_input': {'command': command}}, **extra)


def test_redirect_keeps_a_bare_digit_argument():
    assert m.redirected_argv('echo 2 > out.txt') == (('echo', '2'), (('>', 'out.txt'),))
    assert m.redirected_argv('ls 2>err.txt') == (('ls',), (('>', 'err.txt'),))


def test_mv_with_several_sources_removes_each():
    effects = m.effects(bash('mv a.txt b.txt dest/'))
    assert {e['subject'] for e in effects if e.get('removed')} == {'a.txt', 'b.txt'}


def test_deeply_nested_json_payload_does_not_raise():
    event = {'hook_event_name': 'PreToolUse', 'tool_name': 'Write', 'cwd': '/tmp', 'session_id': 's',
             'tool_input': {'file_path': '/tmp/x.txt', 'content': '[' * 100000 + ']' * 100000}}
    m.edited_forms(event, 'file:/tmp/x.txt')
