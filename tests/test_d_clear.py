"""A rule-d hold names one action that already pays rule d for its subject, and that action clears it."""
import pytest

from test_rules import call, ev, read, send, stop


def write(path, content, tid='write'):
    """A Write of PATH whose content an earlier reading supplies, so only rule d can hold what follows."""
    return read(content, 'spec_' + tid) + call('Write', {'file_path': path, 'content': content}, {'content': 'ok'}, tid)


def bash(command, stdout='', tid='clear'):
    return call('Bash', {'command': command}, {'stdout': stdout, 'exitCode': 0}, tid)


GENERAL = 'Clear: Run it as its own Bash command, with no loop, variable, heredoc or subshell, and read its output.'
KINDS = {
    # kind: (written path, content, the Clear sentence, the events of the action it names)
    'python module': ('app/mod.py', 'VALUE = 1\n',
                      'Clear: Run python3 -c "import app.mod" as its own Bash command and read its output.',
                      bash('python3 -c "import app.mod"')),
    'python package': ('app/__init__.py', 'VALUE = 1\n',
                       'Clear: Run python3 -c "import app" as its own Bash command and read its output.',
                       bash('python3 -c "import app"')),
    'data file': ('config.json', '{"value": 1}\n',
                  'Clear: Run cat config.json as its own Bash command and read its output.',
                  bash('cat config.json', '{"value": 1}\n')),
    'other code': ('tool.js', 'console.log(1)\n', GENERAL, bash('node tool.js', '1\n')),
}


@pytest.mark.parametrize('kind', sorted(KINDS))
def test_the_clear_sentence_names_an_action_that_pays_rule_d(tmp_path, kind):
    path, content, sentence, action = KINDS[kind]
    for event in write(path, content):
        assert send(tmp_path, event) == {}
    held = send(tmp_path, stop('Done'))
    assert held.get('decision') == 'block' and held['reason'].startswith('makoto rule d ')
    assert held['reason'].count('Clear: ') == 1 and sentence in held['reason']
    for event in action:
        assert send(tmp_path, event) == {}
    assert send(tmp_path, stop('Done')) == {}, 'the named action must clear the hold'


def test_a_python_file_outside_the_cwd_gets_the_general_sentence(tmp_path):
    for event in write('../elsewhere/mod.py', 'VALUE = 1\n'):
        assert send(tmp_path, event) == {}
    held = send(tmp_path, stop('Done'))
    assert held['reason'].startswith('makoto rule d ') and GENERAL in held['reason']


def test_an_edit_naming_an_unrun_module_is_held_with_the_import_that_clears_it(tmp_path):
    user = 'from app.core import credit\nTOTAL = credit\n'
    core = 'def credit(x):\n    return x\n'
    edit = ev('PreToolUse', tool_name='Edit', tool_use_id='edit',
              tool_input={'file_path': 'app/user.py', 'old_string': 'TOTAL = credit', 'new_string': 'TOTAL = credit(1)'})
    for event in call('Read', {'file_path': 'app/user.py'}, {'content': user}, 'read_user') + write('app/core.py', core):
        assert send(tmp_path, event) == {}
    held = send(tmp_path, edit)
    reason = held['hookSpecificOutput']['permissionDecisionReason']
    assert held['hookSpecificOutput']['permissionDecision'] == 'deny' and reason.startswith('makoto rule d ')
    assert 'Clear: Run python3 -c "import app.core" as its own Bash command and read its output.' in reason
    for event in bash('python3 -c "import app.core"'):
        assert send(tmp_path, event) == {}
    assert send(tmp_path, edit) == {}, 'the named import must clear the hold on the edit'
