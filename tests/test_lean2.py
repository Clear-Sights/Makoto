"""Rule d lean2: a run of a program pays the files in its static import closure (through hooks.json)."""
import json
import os
from pathlib import Path
import subprocess

PLUGIN = Path(__file__).resolve().parents[1] / 'plugin'
HOOKS = json.loads((PLUGIN / 'hooks' / 'hooks.json').read_text(encoding='utf-8'))['hooks']


def send(tmp, event):
    command = HOOKS[event['hook_event_name']][0]['hooks'][0]['command']
    env = {k: v for k, v in os.environ.items() if not k.startswith('MAKOTO_')}
    env.update(CLAUDE_PLUGIN_ROOT=str(PLUGIN), MAKOTO_STATE_DIR=str(tmp / 'state'), PYTHONDONTWRITEBYTECODE='1')
    run = subprocess.run(['bash', '-c', command], input=json.dumps(event), env=env,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


class Session:
    def __init__(self, tmp):
        self.tmp, self.cwd, self.n = tmp, tmp / 'work', 0
        self.cwd.mkdir()
        (self.cwd / 'app').mkdir()

    def ev(self, name, **fields):
        return dict(hook_event_name=name, session_id='lean2', cwd=str(self.cwd), **fields)

    def call(self, tool, tool_input, response):
        self.n += 1
        tid = 't%d' % self.n
        for event in (self.ev('PreToolUse', tool_name=tool, tool_use_id=tid, tool_input=tool_input),
                      self.ev('PostToolUse', tool_name=tool, tool_use_id=tid, tool_input=tool_input, tool_response=response)):
            assert send(self.tmp, event) == {}

    def write(self, path, text):
        (self.cwd / path).write_text(text, encoding='utf-8')
        self.call('Write', {'file_path': path, 'content': text}, {'content': 'ok'})

    def run(self, command):
        self.call('Bash', {'command': command}, {'stdout': '1\n', 'exitCode': 0})

    def stop(self):
        return send(self.tmp, self.ev('Stop', last_assistant_message='Done', stop_hook_active=True))


def start(tmp):
    s = Session(tmp)
    s.write('app/mod.py', 'def f():\n    return 1\n')
    return s


def held(response):
    return response.get('decision') == 'block' and response['reason'].startswith('makoto rule d ')


def test_a_run_of_importer_pays_edited_module(tmp_path):
    s = start(tmp_path)
    s.write('show.py', 'import app.mod\nprint(app.mod.f())\n')
    s.run('python3 show.py')
    assert s.stop() == {}


def test_b_script_not_importing_it_stays_held(tmp_path):
    s = start(tmp_path)
    s.write('other.py', 'print(2)\n')
    s.run('python3 other.py')
    assert held(s.stop())


def test_c_edit_after_run_is_held(tmp_path):
    s = start(tmp_path)
    s.write('show.py', 'import app.mod\nprint(app.mod.f())\n')
    s.run('python3 show.py')
    s.write('app/mod.py', 'def f():\n    return 2\n')
    assert held(s.stop())


def test_d_cwd_module_named_like_stdlib_is_paid(tmp_path):
    s = Session(tmp_path)
    s.write('calendar.py', 'X = 1\n')
    s.write('app/view.py', 'import calendar\n')
    s.write('show.py', 'import app.view\n')
    s.run('python3 show.py')
    assert s.stop() == {}
