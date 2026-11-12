"""Makoto, end to end through the hooks.json command (one subprocess per hook event), on real temp directories."""
import json
import os
import subprocess
import shutil
import socket
import tempfile
import time
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / 'plugin'
HOOKS = json.loads((PLUGIN / 'hooks' / 'hooks.json').read_text(encoding='utf-8'))['hooks']
SH = '#!/bin/sh\necho 1\n'
MODULE = 'import lib\n'
USERS = ['u1.py', 'u2.py', 'u3.py']


def hold(unchecked, entries):
    return 'Not run since a change: %s. Run %s and read the output.' % (', '.join(sorted(unchecked)), ', '.join(entries))


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


def unshared():
    return subprocess.run(['unshare', '-rn', 'true'], capture_output=True).returncode == 0


needs_isolation = pytest.mark.skipif(not unshared(), reason='unshare -rn does not work here')


def without_isolation(tmp):
    """A PATH that has what the hook needs but neither unshare nor sandbox-exec."""
    bin = tmp / 'bin'
    bin.mkdir(exist_ok=True)
    for name in ('python3', 'bash', 'git', 'sh', 'env'):
        if shutil.which(name) and not (bin / name).exists():
            (bin / name).symlink_to(shutil.which(name))
    return str(bin)


class Session:
    """Probes are off (no isolation on PATH) unless iso is true, so the set rules are tested alone."""

    def __init__(self, tmp, git, files=None, iso=False):
        self.iso, self.env = iso, {}
        self.tmp, self.cwd, self.clock = tmp, tmp / 'work', time.time() - 1000
        self.cwd.mkdir()
        for name, text in (files or {}).items():
            self.put(name, text)
        if git:
            subprocess.run(['git', 'init', '-q'], cwd=self.cwd, check=True)
        self.send('SessionStart')

    def send(self, name, **fields):
        extra = dict(self.env) if self.iso else dict(self.env, PATH=without_isolation(self.tmp))
        return send(self.tmp, dict(hook_event_name=name, session_id='s', cwd=str(self.cwd), **fields), **extra)

    def put(self, path, text='x = 1\n'):
        """Write a file whose modified time is a new moment on a clock that starts in the past."""
        (self.cwd / path).parent.mkdir(parents=True, exist_ok=True)
        (self.cwd / path).write_text(text, encoding='utf-8')
        self.clock += 10
        os.utime(self.cwd / path, (self.clock, self.clock))

    def call(self, tool, tool_input):
        return self.send('PostToolUse', tool_name=tool, tool_use_id='t', tool_input=tool_input, tool_response={'stdout': '1\n'})

    def call_out(self, command, stdout, stderr=''):
        return self.send('PostToolUse', tool_name='Bash', tool_use_id='t', tool_input={'command': command},
                         tool_response={'stdout': stdout, 'stderr': stderr})

    def edit(self, path, text='x = 1\n'):
        self.put(path, text)
        return self.call('Write', {'file_path': path, 'content': text})

    def sh(self, command):
        return self.call('Bash', {'command': command})

    def fail(self, command):
        return self.send('PostToolUseFailure', tool_name='Bash', tool_use_id='t', tool_input={'command': command}, error='exit 1')

    def stop(self, name='Stop', **fields):
        return self.send(name, last_assistant_message='Done', **fields)



def snapshot_fan(tmp_path):
    return Session(tmp_path, False, {'lib.py': 'x = 1\n', 'u1.py': MODULE, 'u2.py': MODULE, 'u3.py': MODULE,
                                        'main.py': 'import u1\nimport u2\nimport u3\n'})


def test_width_0_chat_session_has_no_message(s):
    assert s.stop() == {}
    assert s.stop('SubagentStop') == {}


def test_width_1_script_nothing_uses(s):
    assert s.edit('tool', SH) == {}  # no note in this variant
    assert s.stop() == {'decision': 'block', 'reason': hold(['tool'], ['tool'])}
    s.sh('./tool')
    assert s.stop() == {}


def test_file_outside_the_lookup_without_shebang_is_not_demanded(s):
    assert s.edit('a.py', 'print(1)\n') == {}
    assert s.edit('data.json', '{}') == {}
    assert s.stop() == {}


def test_markdown_is_not_demanded(s):
    s.edit('NOTES.md', '# notes\n')
    assert s.stop() == {}


def test_width_n_module_with_three_users(tmp_path):
    s = snapshot_fan(tmp_path)
    everyone = ['lib.py', 'main.py'] + USERS
    assert s.edit('lib.py', 'x = 2\n') == {}
    assert s.edit('lib.py', 'x = 3\n') == {}
    assert s.stop()['reason'] == hold(everyone, ['main.py'])
    s.sh('python3 u1.py')  # reaches u1 and lib only
    assert s.stop(stop_hook_active=True) == {}
    assert s.stop()['reason'] == hold(['main.py', 'u2.py', 'u3.py'], ['main.py'])
    s.sh('python3 main.py')  # reaches all
    assert s.stop() == {}


def test_entry_program_that_reaches_all_checks_all(tmp_path):
    s = snapshot_fan(tmp_path)
    s.edit('lib.py', 'x = 2\n')
    s.sh('cd . && python3 main.py 2>&1 | tail -3')
    assert s.stop() == {}


def test_a_run_before_a_change_does_not_check_a_user(tmp_path):
    s = snapshot_fan(tmp_path)
    s.clock = time.time() + 100
    s.sh('python3 u2.py')
    s.edit('lib.py', 'x = 2\n')
    assert 'u2.py' in s.stop()['reason']


def test_failed_run_does_not_check(tmp_path):
    s = snapshot_fan(tmp_path)
    s.edit('lib.py', 'x = 2\n')
    s.fail('python3 main.py')
    assert s.stop()['decision'] == 'block'
    s.call_out('python3 main.py', 'Traceback (most recent call last):\n  File "x"\nValueError: no\n')
    assert s.stop()['decision'] == 'block'
    s.call_out('python3 main.py', 'all about the error in prose\n')
    assert s.stop() == {}


def test_reedit_after_check_notes_again(tmp_path):
    s = snapshot_fan(tmp_path)
    s.edit('lib.py', 'x = 2\n')
    s.sh('python3 main.py')
    s.clock = time.time() + 100
    assert s.edit('lib.py', 'x = 3\n') == {}
    assert s.stop()['decision'] == 'block'


@pytest.mark.parametrize('command', ['pytest', 'python3 -m pytest -q', 'go test ./...', 'cargo test', 'npm test', 'make'])
def test_test_runner_without_program_reaches_every_file(tmp_path, command):
    s = snapshot_fan(tmp_path)
    s.edit('lib.py', 'x = 2\n')
    s.sh(command)
    assert s.stop() == {}


def test_test_runner_with_a_program_reaches_only_that_program(tmp_path):
    s = snapshot_fan(tmp_path)
    s.edit('lib.py', 'x = 2\n')
    s.sh('pytest u3.py')
    assert s.stop()['reason'] == hold(['main.py', 'u1.py', 'u2.py'], ['main.py'])


def test_unrelated_run_does_not_check(tmp_path):
    s = snapshot_fan(tmp_path)
    s.put('other.py', 'print(1)\n')
    s.edit('lib.py', 'x = 2\n')
    s.sh('python3 other.py && ls && cat lib.py && git status')
    assert s.stop()['decision'] == 'block'


@pytest.mark.parametrize('user,text,used,used_text', [
    ('app.js', "const m = require('./util')\n", 'util.js', 'module.exports = 1\n'),
    ('app.js', "import x from '../lib/util.js'\n", 'lib/util.js', 'export default 1\n'),
    ('a.c', '#include "util.h"\n', 'util.h', 'int x;\n'),
    ('run.sh', '#!/bin/sh\nsource ./env.sh\n', 'env.sh', 'X=1\n'),
    ('app.rb', "require_relative 'util'\n", 'util.rb', 'X = 1\n'),
    ('app.php', "<?php include 'util.php';\n", 'util.php', '<?php $x = 1;\n'),
    ('pkg/app.py', 'from pkg.util import f\n', 'pkg/util.py', 'def f(): pass\n'),
    ('main.rs', 'use crate::util::f;\n', 'util.rs', 'pub fn f() {}\n'),
])
def test_lookup_reads_import_style_lines(tmp_path, user, text, used, used_text):
    s = Session(tmp_path, False, {user: text, used: used_text})
    s.edit(used, used_text + '\n')
    assert s.stop()['reason'] == hold([used, user], [user])


def test_lookup_is_refreshed_for_changed_files(tmp_path):
    s = Session(tmp_path, False, {'lib.py': 'x = 1\n', 'new.py': 'y = 1\n'})
    s.edit('new.py', 'import lib\n')  # new.py now uses lib; lib itself is untouched
    s.edit('lib.py', 'x = 2\n')
    assert s.stop()['reason'] == hold(['lib.py', 'new.py'], ['new.py'])


def test_change_made_by_a_script_is_seen(s):
    s.put('gen.py', SH)
    (s.cwd / 'out.sh').write_text('#!/bin/sh\n')
    s.sh('./gen.py')
    assert s.stop()['reason'] == hold(['out.sh'], ['out.sh'])


def test_pre_session_changes_are_not_held(tmp_path):
    s = Session(tmp_path, False, {'dirty.py': SH})
    assert s.stop() == {}


@pytest.mark.parametrize('folder', ['target', 'build', 'dist'])
def test_folder_named_like_build_output_is_the_users_unless_git_ignores_it(tmp_path, folder):
    s = Session(tmp_path, False)
    s.edit(folder + '/tool', SH)
    assert s.stop()['reason'] == hold([folder + '/tool'], [folder + '/tool'])


@pytest.mark.parametrize('folder', ['node_modules', '__pycache__', '.venv', 'venv', '.git'])
def test_five_names_are_skipped(tmp_path, folder):
    s = Session(tmp_path, False)
    s.edit(folder + '/tool', SH)
    assert s.stop() == {}


def test_git_ignored_files_are_skipped(tmp_path):
    s = Session(tmp_path, True)
    s.put('.gitignore', 'out/\n')
    s.send('UserPromptSubmit', prompt='x')
    s.edit('out/tool', SH)
    assert s.stop() == {}


def test_second_stop_is_admitted_when_nothing_was_probed(s):
    s.edit('tool', SH)
    assert s.stop()['decision'] == 'block'
    assert s.stop(stop_hook_active=True) == {}


def test_infrastructure_errors_block_with_the_disable_text(tmp_path):
    s = Session(tmp_path, False)
    bad = send(tmp_path, dict(hook_event_name='Stop', cwd=str(s.cwd)))  # no session id
    assert bad['decision'] == 'block' and 'claude plugin disable makoto' in bad['reason']
    state = tmp_path / 'state'
    (state / next(p for p in os.listdir(state) if p.endswith('.json'))).write_text('{"snapshot": 5}')
    err = s.stop()
    assert err['decision'] == 'block' and 'claude plugin disable makoto' in err['reason']


def test_prompt_and_session_start_are_never_blocked(tmp_path):
    for name in ('SessionStart', 'UserPromptSubmit'):
        assert send(tmp_path, dict(hook_event_name=name, cwd=str(tmp_path))) == {}  # no session id
    run = subprocess.run(['bash', '-c', HOOKS['Stop'][0]['hooks'][0]['command']], input='not json', capture_output=True,
                         text=True, env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN), MAKOTO_STATE_DIR=str(tmp_path)))
    assert json.loads(run.stdout)['decision'] == 'block'


def test_hooks_have_timeouts():
    for groups in HOOKS.values():
        assert all(h['timeout'] >= 10 for g in groups for h in g['hooks'])
    assert all(h['timeout'] == 30 for k in ('Stop', 'SubagentStop') for g in HOOKS[k] for h in g['hooks'])


def test_code_computing_the_sets_does_not_test_a_size():
    import ast
    tree = ast.parse((PLUGIN / 'makoto2.py').read_text(encoding='utf-8'))
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('close', 'sets', 'lookup')):
        nodes = list(ast.walk(fn))
        assert not [n for n in nodes if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'len'], fn.name
        assert not [n for n in nodes if isinstance(n, ast.If) and not isinstance(n.test, ast.Compare)], fn.name  # membership only
        assert not [n for n in nodes if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not)], fn.name


# ---------------------------------------------------------------- the probe

def tree(tmp, **extra):
    """lib.py, three users and main.py, all unchanged at session start, with probes on."""
    files = {'lib.py': 'x = 1\n', 'u1.py': MODULE, 'u2.py': MODULE, 'u3.py': MODULE,
             'main.py': 'import u1\nimport u2\nimport u3\nprint("ran")\n'}
    files.update(extra)
    return Session(tmp, False, files, iso=True)


@needs_isolation
def test_probe_passes_silently_and_checks_what_it_reaches(tmp_path):
    s = tree(tmp_path)
    assert s.edit('lib.py', 'x = 2\n') == {}
    assert s.stop() == {}
    s.edit('lib.py', 'x = 3\n')
    assert s.stop('SubagentStop') == {}


@needs_isolation
def test_probe_that_fails_holds_with_the_output_at_most_three_times(tmp_path):
    s = tree(tmp_path)
    s.edit('lib.py', 'print("line %d" % i) if False else None\nfor i in range(30):\n    print("line", i)\nraise SystemExit(3)\n')
    reason = s.stop()['reason']
    assert reason.startswith(hold(['lib.py', 'main.py', 'u1.py', 'u2.py', 'u3.py'], ['main.py']))
    assert 'Probe of main.py failed' in reason and 'line 29' in reason and 'line 15\n' in reason and 'line 14\n' not in reason
    assert s.stop(stop_hook_active=True)['decision'] == 'block'
    assert s.stop(stop_hook_active=True)['decision'] == 'block'
    assert s.stop(stop_hook_active=True) == {}  # the fourth is admitted
    assert s.stop()['decision'] == 'block'  # a new final answer starts over


@needs_isolation
def test_probe_fixed_after_a_hold_is_admitted_silently(tmp_path):
    s = tree(tmp_path)
    s.edit('lib.py', 'raise SystemExit(1)\n')
    assert s.stop()['decision'] == 'block'
    s.edit('lib.py', 'x = 5\n')
    assert s.stop(stop_hook_active=True) == {}


def test_without_isolation_it_holds_as_set_does_once(tmp_path):
    s = Session(tmp_path, False, {'lib.py': 'x = 1\n', 'main.py': 'import lib\nraise SystemExit(1)\n'})
    s.edit('lib.py', 'x = 2\n')
    assert s.stop() == {'decision': 'block', 'reason': hold(['lib.py', 'main.py'], ['main.py'])}
    assert s.stop(stop_hook_active=True) == {}


@needs_isolation
def test_probe_cannot_write_into_the_tree_or_reach_the_network(tmp_path):
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    server.settimeout(0.5)
    script = ('#!/bin/bash\nimport_marker=1\necho leaked > leak.txt\necho leaked > ../leak2.txt\n'
              'exec 3<>/dev/tcp/127.0.0.1/%d || { echo NOCONNECT; exit 3; }\necho CONNECTED\n' % server.getsockname()[1])
    s = Session(tmp_path, False, {'probe_net': script, 'lib.py': 'x = 1\n'}, iso=True)
    (tmp_path / 'tmp').mkdir()
    s.env['TMPDIR'] = str(tmp_path / 'tmp')
    before = sorted(p.name for p in tmp_path.rglob('*'))
    s.edit('probe_net', script + '# changed\n')
    reason = s.stop()['reason']
    assert 'NOCONNECT' in reason and 'CONNECTED\n' not in reason.replace('NOCONNECT', '')
    with pytest.raises(socket.timeout):
        server.accept()
    assert not (s.cwd / 'leak.txt').exists() and not (tmp_path / 'leak2.txt').exists()
    assert sorted(p.name for p in tmp_path.rglob('*')) == before
    assert os.listdir(tmp_path / 'tmp') == []  # the temporary copy is deleted
    server.close()


@needs_isolation
def test_probe_environment_input_and_directory(tmp_path):
    s = Session(tmp_path, False, {'sub/tool': '#!/bin/sh\n', 'sub/lib.sh': 'X=1\n'}, iso=True)
    s.env['MAKOTO_SECRET'] = 'hunter2'
    script = '#!/bin/sh\n. ./lib.sh\nenv | sort\npwd\nif read -r line; then echo GOTINPUT; else echo STDIN_CLOSED; fi\nexit 1\n'
    s.edit('sub/tool', script)
    reason = send(tmp_path, dict(hook_event_name='Stop', session_id='s', cwd=str(s.cwd / 'sub')),
                  PATH=os.environ['PATH'], MAKOTO_SECRET='hunter2')['reason']
    assert 'hunter2' not in reason and 'STDIN_CLOSED' in reason and 'HOME=' in reason
    assert '/tree/sub' in reason  # the same relative cwd, inside the copy


@needs_isolation
def test_probe_that_times_out_is_not_a_failure(tmp_path):
    s = Session(tmp_path, False, {'lib.py': 'x = 1\n', 'main.py': 'import lib\n'}, iso=True)
    s.edit('main.py', 'import lib\nimport time\ntime.sleep(60)\n')
    started = time.time()
    assert s.stop()['reason'] == hold(['main.py'], ['main.py'])
    assert time.time() - started < 25


@needs_isolation
def test_nothing_is_probed_over_the_size_cap(tmp_path):
    s = Session(tmp_path, False, {'lib.py': 'x = 1\n', 'main.py': 'import lib\n'}, iso=True)
    with open(s.cwd / 'big.bin', 'wb') as big:
        big.truncate(51 * 1024 * 1024)
    s.edit('main.py', 'import lib\nraise SystemExit(1)\n')
    assert s.stop()['reason'] == hold(['main.py'], ['main.py'])


@needs_isolation
def test_entry_that_imports_subprocess_is_not_probed(tmp_path):
    s = Session(tmp_path, False, {'lib.py': 'x = 1\n', 'main.py': 'import lib\n'}, iso=True)
    s.edit('main.py', 'import lib\nimport subprocess\nraise SystemExit(1)\n')
    assert s.stop() == {'decision': 'block', 'reason': hold(['main.py'], ['main.py'])}  # held as set: no probe output


@needs_isolation
def test_entry_reaching_subprocess_through_a_module_is_not_probed(tmp_path):
    s = Session(tmp_path, False, {'lib.py': 'x = 1\n', 'mid.py': 'import lib\n', 'main.py': 'import mid\nraise SystemExit(1)\n'}, iso=True)
    s.edit('lib.py', 'import subprocess\n')
    assert s.stop()['reason'] == hold(['lib.py', 'main.py', 'mid.py'], ['main.py'])


@needs_isolation
def test_entry_with_no_outward_reach_is_probed(tmp_path):
    s = Session(tmp_path, False, {'lib.py': 'x = 1\n', 'main.py': 'import lib\nraise SystemExit(1)\n'}, iso=True)
    s.edit('lib.py', 'x = 2\n')
    assert 'Probe of main.py failed' in s.stop()['reason']


@needs_isolation
def test_an_entry_the_probe_cannot_run_is_held_as_set(tmp_path):
    s = Session(tmp_path, False, {'lib.go': 'package lib\n', 'main.go': 'import "lib"\n'}, iso=True)
    s.edit('lib.go', 'package lib // 2\n')
    assert s.stop()['reason'] == hold(['lib.go', 'main.go'], ['main.go'])
