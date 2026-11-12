"""Makoto, end to end through the hooks.json command (one subprocess per hook event), on real temp directories."""
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / 'plugin'
HOOKS = json.loads((PLUGIN / 'hooks' / 'hooks.json').read_text(encoding='utf-8'))['hooks']
HOLD = ('makoto rule d [switch]: "%s": Unchanged: Do not assume what can change has not. Missing: a run of it, '
        'with its output read, after its last edit. Clear: Run it and read its output.')
NOTE = 'Before your final answer, run the program or tests that use %s and read the output.'


def send(tmp, event, **extra):
    command = HOOKS[event['hook_event_name']][0]['hooks'][0]['command']
    env = {k: v for k, v in os.environ.items() if not k.startswith('MAKOTO_')}
    env.update(CLAUDE_PLUGIN_ROOT=str(PLUGIN), MAKOTO_STATE_DIR=str(tmp / 'state'), PYTHONDONTWRITEBYTECODE='1')
    env.update(extra)
    run = subprocess.run(['bash', '-c', command], input=json.dumps(event), env=env, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


@pytest.fixture(params=['no git', 'git'])
def s(request, tmp_path):
    return Session(tmp_path, request.param == 'git')


class Session:
    def __init__(self, tmp, git, files=None):
        self.tmp, self.cwd, self.clock = tmp, tmp / 'work', time.time() - 1000
        self.cwd.mkdir()
        for name, text in (files or {}).items():
            self.put(name, text)
        if git:
            subprocess.run(['git', 'init', '-q'], cwd=self.cwd, check=True)
        self.send('SessionStart')

    def send(self, name, **fields):
        return send(self.tmp, dict(hook_event_name=name, session_id='s', cwd=str(self.cwd), **fields))

    def put(self, path, text='x = 1\n'):
        """Write a file whose modified time is a new moment on a clock that starts in the past."""
        (self.cwd / path).parent.mkdir(parents=True, exist_ok=True)
        (self.cwd / path).write_text(text, encoding='utf-8')
        self.clock += 10
        os.utime(self.cwd / path, (self.clock, self.clock))

    def call(self, tool, tool_input):
        return self.send('PostToolUse', tool_name=tool, tool_use_id='t', tool_input=tool_input, tool_response={'stdout': '1\n'})

    def edit(self, path, text='x = 1\n'):
        self.put(path, text)
        return self.call('Write', {'file_path': path, 'content': text})

    def sh(self, command):
        return self.call('Bash', {'command': command})

    def stop(self, name='Stop', **fields):
        return self.send(name, last_assistant_message='Done', **fields)


LANGUAGES = [('a.py', 'print(1)\n', 'python3 a.py'), ('a.js', 'console.log(1)\n', 'node a.js'),
             ('main.go', 'package main\n', 'go run main.go'), ('main.rs', 'fn main() {}\n', 'cargo run'),
             ('a.rb', 'puts 1\n', 'ruby a.rb'), ('a.sh', 'echo 1\n', 'bash a.sh'), ('tool', '#!/bin/sh\necho 1\n', './tool')]


@pytest.mark.parametrize('name,text,command', LANGUAGES)
def test_edit_then_run_is_admitted(s, name, text, command):
    s.edit(name, text)
    s.sh(command)
    assert s.stop() == {}


@pytest.mark.parametrize('name,text,command', LANGUAGES)
def test_edit_then_stop_is_held(s, name, text, command):
    s.edit(name, text)
    assert s.stop() == {'decision': 'block', 'reason': HOLD % name}
    assert s.stop('SubagentStop')['reason'] == HOLD % name


def test_change_made_by_a_script_is_held(s):
    s.put('gen.py')
    (s.cwd / 'out.js').write_text('1')  # no Write, Edit or shell parsing: only the file system shows it
    s.sh('python3 gen.py')
    assert s.stop()['reason'] == HOLD % 'out.js'


def test_pre_session_dirty_file_is_not_held(tmp_path):
    s = Session(tmp_path, False, {'dirty.py': 'x = 0\n', 'ok.json': '{}'})
    assert s.stop() == {}


def test_run_before_the_change_does_not_pay(s):
    s.sh('python3 a.py')
    s.clock = time.time() + 100
    s.edit('a.py')
    assert s.stop()['reason'] == HOLD % 'a.py'


def test_unrelated_run_does_not_pay(s):
    s.edit('app/a.py')
    s.put('tools/other.py')
    s.sh('python3 tools/other.py && echo done')
    assert s.stop()['reason'] == HOLD % 'app/a.py'


def test_non_run_commands_do_not_pay(s):
    s.edit('a.py')
    s.sh('ls && cat a.py && git status')
    assert s.stop()['reason'] == HOLD % 'a.py'


def test_runs_that_reach_the_file_pay(s):
    s.edit('app/a.py')
    s.put('app/main.py')
    s.edit('web/b.js')
    s.edit('lib/c.py')
    s.sh('cd app && python3 main.py 2>&1 | tail -3')  # a program in the same top-level folder
    s.sh('node web/b.js')  # names the file
    assert s.stop()['reason'] == HOLD % 'lib/c.py'
    s.sh('FOO=1 pytest -q')  # project-wide
    assert s.stop() == {}


def test_second_stop_is_admitted(s):
    s.edit('a.py')
    assert s.stop()['decision'] == 'block'
    assert s.stop(stop_hook_active=True) == {}


def test_failed_run_does_not_pay(s):
    s.edit('a.py')
    s.send('PostToolUseFailure', tool_name='Bash', tool_use_id='t', tool_input={'command': 'python3 a.py'}, error='x')
    assert s.stop()['reason'] == HOLD % 'a.py'


def test_config_paid_by_full_read_after_the_change(s):
    s.edit('c.json', '{"a": 1}\n')
    s.call('Read', {'file_path': 'c.json', 'limit': 1})
    assert s.stop()['reason'] == HOLD % 'c.json'
    s.call('Read', {'file_path': 'c.json'})
    assert s.stop() == {}


def test_config_paid_by_cat_or_run(s):
    s.edit('c.yaml', 'a: 1\n')
    s.edit('d.toml', 'a = 1\n')
    s.sh('cat c.yaml')
    assert s.stop()['reason'] == HOLD % 'd.toml'
    s.sh('make test')
    assert s.stop() == {}


def test_markdown_is_not_held(s):
    for name in ('README.md', 'notes.txt', 'doc.rst'):
        assert s.edit(name, 'hello\n') == {}
    assert s.stop() == {}


def test_note_text_and_once_only(s):
    assert s.edit('src/a.py')['hookSpecificOutput'] == {'hookEventName': 'PostToolUse', 'additionalContext': NOTE % 'src/a.py'}
    assert s.edit('src/a.py', 'x = 2\n') == {}
    s.sh('python3 src/a.py')
    s.clock = time.time() + 100
    assert s.edit('src/a.py', 'x = 3\n')['hookSpecificOutput']['additionalContext'] == NOTE % 'src/a.py'


def test_payment_then_reedit_holds_again(s):
    s.edit('a.py')
    s.sh('python3 a.py')
    assert s.stop() == {}
    s.clock = time.time() + 100
    s.edit('a.py', 'x = 2\n')
    assert s.stop()['reason'] == HOLD % 'a.py'


def test_infrastructure_errors_block_with_the_disable_text(tmp_path):
    s = Session(tmp_path, False)
    blocked = send(tmp_path, dict(hook_event_name='Stop', session_id='s', cwd=str(s.cwd)), MAKOTO_STATE_DIR='/proc/makoto/none')
    assert blocked['decision'] == 'block'
    assert blocked['reason'].startswith('makoto infrastructure error, step blocked: ')
    assert blocked['reason'].endswith('To disable Makoto run in a terminal: claude plugin disable makoto')
    command = HOOKS['Stop'][0]['hooks'][0]['command']
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN), MAKOTO_STATE_DIR=str(tmp_path / 's'))
    run = subprocess.run(['bash', '-c', command], input='not json', env=env, capture_output=True, text=True)
    assert 'claude plugin disable makoto' in json.loads(run.stdout)['reason']


def test_prompt_and_session_start_are_never_blocked(tmp_path):
    for name in ('UserPromptSubmit', 'SessionStart'):
        out = send(tmp_path, dict(hook_event_name=name, session_id='s', cwd=str(tmp_path)), MAKOTO_STATE_DIR='/proc/x')
        assert out == {}


def test_hooks_have_timeouts():
    assert sorted(HOOKS) == ['PostToolUse', 'PostToolUseFailure', 'SessionStart', 'Stop', 'SubagentStop', 'UserPromptSubmit']
    assert all(h[0]['hooks'][0]['timeout'] == 10 for h in HOOKS.values())
