"""Makoto, end to end through the hooks.json command (one subprocess per hook event), on real temp directories."""
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

SRT = Path(os.environ.get('MAKOTO_SRT_TEST') or '/tmp/claude-0/-home-user/a404ef3c-b256-5c21-a29c-bd27a2f29734/scratchpad/srt/node_modules/.bin/srt')
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
    env.update(CLAUDE_PLUGIN_ROOT=str(PLUGIN), MAKOTO_STATE_DIR=str(tmp / 'state'), PYTHONDONTWRITEBYTECODE='1',
               MAKOTO_SRT=str(tmp / 'no-srt'))  # no srt unless a test names one: 6.2.2's behaviour
    env.update(extra)
    run = subprocess.run(['bash', '-c', command], input=json.dumps(event), env=env, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


@pytest.fixture(params=['no git', 'git'])
def s(request, tmp_path):
    return Session(tmp_path, request.param == 'git')


class Session:
    def __init__(self, tmp, git, files=None):
        self.tmp, self.cwd, self.clock, self.env = tmp, tmp / 'work', time.time() - 1000, {}
        self.real = False  # True: files keep their real modified times
        self.cwd.mkdir()
        for name, text in (files or {}).items():
            self.put(name, text)
        if git:
            subprocess.run(['git', 'init', '-q'], cwd=self.cwd, check=True)
        self.send('SessionStart')

    def send(self, name, **fields):
        return send(self.tmp, dict(hook_event_name=name, session_id='s', cwd=str(self.cwd), **fields), **self.env)

    def put(self, path, text='x = 1\n'):
        """Write a file whose modified time is a new moment on a clock that starts in the past."""
        (self.cwd / path).parent.mkdir(parents=True, exist_ok=True)
        (self.cwd / path).write_text(text, encoding='utf-8')
        self.clock += 10
        if not self.real:
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
    note = s.edit('tool', SH)
    assert note['hookSpecificOutput']['additionalContext'] == hold(['tool'], ['tool'])
    assert s.stop() == {'decision': 'block', 'reason': hold(['tool'], ['tool'])}
    s.sh('./tool')
    assert s.stop() == {}


def test_linkless_data_without_shebang_or_script_extension_is_not_demanded(s):
    assert s.edit('a.txt', 'one\n') == {}
    assert s.edit('data.json', '{}') == {}
    assert s.stop() == {}


def test_markdown_is_not_demanded(s):
    s.edit('NOTES.md', '# notes\n')
    assert s.stop() == {}


def test_width_n_module_with_three_users(tmp_path):
    s = snapshot_fan(tmp_path)
    everyone = ['lib.py', 'main.py'] + USERS
    note = s.edit('lib.py', 'x = 2\n')
    assert note['hookSpecificOutput']['additionalContext'] == hold(everyone, ['main.py'])
    assert s.edit('lib.py', 'x = 3\n') == {}  # once per changed file until checked
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


def test_reedit_after_check_gives_no_second_note_for_the_same_entry_program(tmp_path):
    s = snapshot_fan(tmp_path)
    s.edit('lib.py', 'x = 2\n')
    s.sh('python3 main.py')
    s.clock = time.time() + 100
    assert s.edit('lib.py', 'x = 3\n') == {}  # main.py was named by an earlier note
    assert s.stop()['decision'] == 'block'


@pytest.mark.parametrize('command', ['pytest', 'python3 -m pytest -q', 'go test ./...', 'cargo test', 'npm test', 'make'])
def test_test_runner_without_program_reaches_the_test_files_and_what_they_use(tmp_path, command):
    s = snapshot_fan(tmp_path)
    s.put('test_fan.py', 'import main\n')
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


def test_second_stop_is_admitted(s):
    s.edit('tool', SH)
    assert s.stop()['decision'] == 'block'
    assert s.stop(stop_hook_active=True) == {}


def test_infrastructure_errors_block_with_the_disable_text(tmp_path):
    s = Session(tmp_path, False)
    bad = send(tmp_path, dict(hook_event_name='Stop', cwd=str(s.cwd)))  # no session id
    assert bad['decision'] == 'block' and 'claude plugin disable makoto' in bad['reason']
    state = tmp_path / 'state'
    (state / next(p for p in os.listdir(state) if p.endswith('.json'))).write_text('{"nodes": 5}')
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


def test_code_computing_the_sets_does_not_test_a_size():
    import ast
    tree = ast.parse((PLUGIN / 'makoto2.py').read_text(encoding='utf-8'))
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('close', 'sets', 'lookup')):
        nodes = list(ast.walk(fn))
        assert not [n for n in nodes if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'len'], fn.name
        assert not [n for n in nodes if isinstance(n, ast.If) and not isinstance(n.test, ast.Compare)], fn.name  # membership only
        assert not [n for n in nodes if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not)], fn.name


WRITER = 'import json\njson.dump({}, open("out.json", "w"))\n'
READER = 'import json\nprint(json.load(open("out.json")))\n'


def test_linkless_changed_script_is_held(s):
    note = s.edit('solo.py', 'print(1)\n')
    assert note['hookSpecificOutput']['additionalContext'] == hold(['solo.py'], ['solo.py'])
    assert s.stop()['reason'] == hold(['solo.py'], ['solo.py'])
    s.sh('python3 solo.py')
    assert s.stop() == {}


def chain(tmp_path):
    return Session(tmp_path, False, {'writer.py': WRITER, 'reader.py': READER, 'out.json': '{}'})


def test_data_chain_changing_the_writer_demands_the_reader(tmp_path):
    s = chain(tmp_path)
    s.edit('writer.py', WRITER + '\n')
    assert s.stop()['reason'] == hold(['out.json', 'reader.py', 'writer.py'], ['reader.py'])
    s.sh('python3 writer.py')
    assert s.stop()['reason'] == hold(['out.json', 'reader.py'], ['reader.py'])
    s.sh('python3 reader.py')  # reaches out.json and its writer
    assert s.stop() == {}


def test_data_chain_a_run_of_the_reader_alone_checks_both_ends(tmp_path):
    s = chain(tmp_path)
    s.edit('writer.py', WRITER + '\n')
    s.sh('python3 reader.py')
    assert s.stop() == {}


def test_data_chain_a_failed_run_of_the_reader_says_a_run_that_succeeds(tmp_path):
    s = chain(tmp_path)
    s.edit('writer.py', WRITER + '\n')
    s.fail('python3 reader.py')
    assert 'needs a run that succeeds' in s.stop()['reason']


def state_file(tmp_path):
    return next((tmp_path / 'state').glob('*[0-9a-f].json'))


def test_state_is_the_same_size_after_200_runs_as_after_2(tmp_path):
    s = snapshot_fan(tmp_path)
    s.edit('lib.py', 'x = 2\n')
    s.sh('python3 main.py')
    s.sh('python3 u1.py')
    small = state_file(tmp_path).stat().st_size
    for i in range(99):
        s.sh('python3 main.py')
        s.sh('python3 u1.py')
    assert state_file(tmp_path).stat().st_size == small


def test_state_holds_a_map_and_no_list_of_runs_reads_notes_or_unpaid_files(tmp_path):
    s = chain(tmp_path)
    s.edit('writer.py', WRITER + '\n')
    s.sh('python3 writer.py')
    text = state_file(tmp_path).read_text(encoding='utf-8')
    state = json.loads(text)
    assert set(state) == {'root', 'nodes', 'last'}
    assert set(state['nodes']['reader.py']) == {'start', 'ran', 'failed', 'noted', 'hash', 'shebang', 'uses', 'quotes', 'writes'}
    for word in ('runs', 'reads', 'notes', 'unpaid'):
        assert word not in text


def test_passing_test_run_checks_what_the_tests_import_and_leaves_an_unreached_module_demanded(s):
    s.put('lib.py')
    s.put('other.py')
    s.put('tests/check.py', 'import lib\n')
    s.send('UserPromptSubmit', prompt='x')
    s.edit('lib.py', 'x = 2\n')
    s.edit('other.py', 'x = 2\n')
    s.sh('pytest')
    assert s.stop()['reason'] == hold(['other.py'], ['other.py'])


def test_twelve_edits_with_the_same_entry_program_give_one_note(tmp_path):
    s = snapshot_fan(tmp_path)
    notes = [s.edit('lib.py', 'x = %d\n' % i) for i in range(12)]
    assert [n != {} for n in notes] == [True] + [False] * 11
    assert s.stop()['decision'] == 'block'


def test_a_new_entry_program_gives_a_second_note(tmp_path):
    s = Session(tmp_path, False, {'lib.py': 'x = 1\n', 'a.py': 'import lib\n', 'lib2.py': 'y = 1\n', 'b.py': 'import lib2\n'})
    assert s.edit('lib.py', 'x = 2\n')['hookSpecificOutput']['additionalContext'] == hold(['a.py', 'lib.py'], ['a.py'])
    assert s.edit('lib.py', 'x = 3\n') == {}
    assert s.edit('lib2.py', 'y = 2\n')['hookSpecificOutput']['additionalContext'] == hold(['a.py', 'b.py', 'lib.py', 'lib2.py'], ['a.py', 'b.py'])


def test_shell_redirects_make_produced_by_and_reads_links(tmp_path):
    s = Session(tmp_path, False, {'run.sh': 'python3 gen.py > out.json\nsort < in.txt\n', 'gen.py': 'print(1)\n',
                                  'out.json': '{}', 'in.txt': 'b\na\n', 'reader.py': READER})
    s.edit('run.sh', 'python3 gen.py > out.json\nsort < in.txt\n\n')
    assert s.stop()['reason'] == hold(['out.json', 'reader.py', 'run.sh'], ['reader.py'])
    s.sh('python3 reader.py')
    assert s.stop() == {}
    s.clock = time.time() + 100
    s.edit('in.txt', 'c\n')
    assert s.stop()['reason'] == hold(['in.txt', 'out.json', 'reader.py', 'run.sh'], ['reader.py'])


def note_of(response):
    return response.get('hookSpecificOutput', {}).get('additionalContext')


@pytest.mark.parametrize('command', ["echo 'x = 2' > lib.py", "sed -i 's/1/2/' lib.py"])
def test_a_file_changed_by_a_bash_call_gets_the_note_after_that_call(tmp_path, command):
    s = snapshot_fan(tmp_path)
    s.put('lib.py', 'x = 2\n')
    assert note_of(s.sh(command)) == hold(['lib.py', 'main.py', 'u1.py', 'u2.py', 'u3.py'], ['main.py'])
    assert s.sh(command) == {}  # the entry program was named by that note


def test_a_bash_call_that_changes_nothing_gets_no_note(tmp_path):
    s = snapshot_fan(tmp_path)
    assert s.sh('ls') == {}
    assert s.call('Read', {'file_path': 'lib.py'}) == {}


def test_a_run_that_checks_the_change_gets_no_note(tmp_path):
    s = snapshot_fan(tmp_path)
    s.put('lib.py', 'x = 2\n')
    assert s.sh('python3 main.py') == {}
    assert s.stop() == {}


def test_a_non_edit_tool_that_follows_a_change_gets_the_note(tmp_path):
    s = snapshot_fan(tmp_path)
    s.put('lib.py', 'x = 2\n')
    assert note_of(s.call('Read', {'file_path': 'lib.py'})) is not None


# ---------------------------------------------------------------- collect: the probe, through srt

needs_srt = pytest.mark.skipif(not SRT.is_file(), reason='srt is not installed here')
NOTE = 'hookSpecificOutput'


def probing(tmp_path, files):
    s = Session(tmp_path, False, files)
    s.env, s.real = {'MAKOTO_SRT': str(SRT)}, True
    return s


def context(reply):
    return reply[NOTE]['additionalContext']


def test_without_srt_the_behaviour_is_6_2_2s(tmp_path):
    s = Session(tmp_path, False, {'a.py': 'print(1)\n'})
    assert context(s.edit('a.py', 'print(2)\n')) == hold(['a.py'], ['a.py'])
    assert s.stop() == {'decision': 'block', 'reason': hold(['a.py'], ['a.py'])}


@needs_srt
def test_passing_probe_checks_silently_and_the_final_answer_is_admitted(tmp_path):
    s = probing(tmp_path, {'lib.py': 'x = 1\n', 'main.py': 'import lib\nprint(lib.x)\n'})
    assert s.edit('lib.py', 'x = 2\n') == {}
    assert s.stop() == {}
    assert s.stop('SubagentStop') == {}


@needs_srt
def test_failing_probe_puts_the_error_in_the_note_and_the_hold(tmp_path):
    s = probing(tmp_path, {'lib.py': 'x = 1\n', 'main.py': 'import lib\nprint(lib.x)\n'})
    note = context(s.edit('lib.py', 'x = 1 / 0\n'))
    assert note.startswith(hold(['lib.py', 'main.py'], ['main.py']))
    assert 'ZeroDivisionError' in note and note.endswith('(run in a sandbox with no network)')
    hold_reply = s.stop()
    assert hold_reply['decision'] == 'block' and 'ZeroDivisionError' in hold_reply['reason']
    assert s.stop(stop_hook_active=True) == {}


@needs_srt
def test_the_same_failure_is_not_noted_twice_but_a_new_one_is(tmp_path):
    s = probing(tmp_path, {'main.py': 'print(1)\n'})
    assert 'ZeroDivisionError' in context(s.edit('main.py', 'print(1 / 0)\n'))
    assert s.edit('main.py', 'print(1 / 0)\n\n') == {}
    assert 'NameError' in context(s.edit('main.py', 'print(undefined_name)\n'))
    assert s.edit('main.py', 'print(1)\n') == {}  # passes: checked


@needs_srt
def test_a_probe_cannot_write_outside_its_copy_or_reach_the_network(tmp_path):
    outside = tmp_path / 'outside.txt'
    program = ('import socket\nopen(%r, "w").write("x")\n' % str(outside)
               + 'socket.create_connection(("1.1.1.1", 53), timeout=2)\n')
    s = probing(tmp_path, {'main.py': 'print(1)\n'})
    note = context(s.edit('main.py', program))
    assert 'main.py' in note and note.endswith('(run in a sandbox with no network)')
    assert not outside.exists()
    assert (s.cwd / 'main.py').read_text() == program and sorted(p.name for p in s.cwd.iterdir()) == ['main.py']


@needs_srt
def test_a_probe_writes_only_in_its_copy_and_the_real_tree_is_unchanged(tmp_path):
    s = probing(tmp_path, {'main.py': 'print(1)\n'})
    s.edit('main.py', 'open("made.txt", "w").write("x")\n')
    assert sorted(p.name for p in s.cwd.iterdir()) == ['main.py']
    assert s.stop() == {}


@needs_srt
@pytest.mark.parametrize('library', ['subprocess', 'socket'])
def test_a_program_that_imports_subprocess_or_socket_is_probed(tmp_path, library):
    s = probing(tmp_path, {'main.py': 'print(1)\n'})
    assert s.edit('main.py', 'import %s\nprint(1)\n' % library) == {}
    assert s.stop() == {}
    assert 'NameError' in context(s.edit('main.py', 'import %s\nundefined_name\n' % library))


@needs_srt
def test_a_timeout_leaves_6_2_2s_note_and_hold(tmp_path):
    s = probing(tmp_path, {'main.py': 'print(1)\n'})
    started = time.time()
    assert context(s.edit('main.py', 'import time\ntime.sleep(60)\n')) == hold(['main.py'], ['main.py'])
    assert time.time() - started < 15
    assert s.stop() == {'decision': 'block', 'reason': hold(['main.py'], ['main.py'])}


@needs_srt
def test_a_program_without_a_known_interpreter_is_not_probed(tmp_path):
    s = probing(tmp_path, {'data.json': '{}', 'main.py': 'import json\njson.load(open("data.json"))\n'})
    assert s.edit('data.json', '{"a": 1}') == {}  # main.py is the entry and passes
    s.put('tool.lua', 'print(1)\n')
    assert context(s.call('Write', {'file_path': 'tool.lua'})) == hold(['tool.lua'], ['tool.lua'])


@needs_srt
def test_a_shell_program_with_a_shebang_is_probed_in_the_same_relative_directory(tmp_path):
    s = probing(tmp_path, {'sub/run': '#!/bin/sh\necho 1\n', 'sub/data.txt': 'a\n'})
    s.cwd = tmp_path / 'work' / 'sub'
    assert s.edit('run', '#!/bin/sh\ncat data.txt\n') == {}
    assert 'No such file' in context(s.edit('run', '#!/bin/sh\ncat nothere.txt\n'))
