"""Synthetic stand-in for the corpus run (the corpus repository could not be attached): sessions that change a
definition with N downstream users, N = 1..12, each as a plant D (every reading of one use file removed), its twin
(all use files read) and a control (no use file exists). Run against the plugin in PLUGIN_DIR (default ../plugin).
    python3 eval/synthetic_downstream.py [--json out.json]"""
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stats import show  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = Path(os.environ.get('PLUGIN_DIR', ROOT / 'plugin'))
CMD = json.loads((PLUGIN / 'hooks' / 'hooks.json').read_text())['hooks']
A = 'def area(w, h):\n    return w * h\n'
EDIT = {'old_string': 'def area(w, h):', 'new_string': 'def area(w, h, unit):'}


def send(state, event):
    command = CMD[event['hook_event_name']][0]['hooks'][0]['command']
    env = {k: v for k, v in os.environ.items() if not k.startswith('MAKOTO_')}
    env.update(CLAUDE_PLUGIN_ROOT=str(PLUGIN), MAKOTO_STATE_DIR=str(state), PYTHONDONTWRITEBYTECODE='1')
    started = time.perf_counter()
    run = subprocess.run(['bash', '-c', command], input=json.dumps(event), env=env, capture_output=True, text=True, timeout=60)
    return json.loads(run.stdout), (time.perf_counter() - started) * 1000, run.returncode


def session(users, unread, sid):
    """(events, final Stop). `unread` use files get no reading."""
    root = Path(tempfile.mkdtemp(prefix='ds-')) / 'repo'
    root.mkdir()
    (root / 'a.py').write_text(A)
    for i in range(users):
        (root / f'u{i}.py').write_text(f'from a import area\nprint(area({i}, 2))\n')
    (root / 'notes.txt').write_text('spec')

    def call(tool, tin, resp, tid):
        base = dict(session_id=sid, cwd=str(root), tool_name=tool, tool_use_id=tid, tool_input=tin)
        return [dict(base, hook_event_name='PreToolUse'), dict(base, hook_event_name='PostToolUse', tool_response=resp)]

    def read(name, text):
        p = str(root / name)
        return call('Read', {'file_path': p}, {'type': 'text', 'file': {'filePath': p, 'content': text}}, 'r-' + name)
    events = read('a.py', A) + call('Edit', dict(EDIT, file_path=str(root / 'a.py')), {'content': 'ok'}, 'e')
    events += call('Bash', {'command': 'python3 a.py'}, {'stdout': '', 'exitCode': 0}, 'run')
    for i in range(users):
        if i not in unread:
            events += read(f'u{i}.py', (root / f'u{i}.py').read_text())
    events += read('notes.txt', 'spec')
    stop = dict(hook_event_name='Stop', session_id=sid, cwd=str(root), last_assistant_message='Done', stop_hook_active=True)
    return events, stop


def play(users, unread, sid):
    events, stop = session(users, unread, sid)
    state = Path(tempfile.mkdtemp(prefix='st-'))
    times, errors = [], 0
    for event in events:
        out, ms, code = send(state, event)
        times.append(ms)
        errors += code != 0 or (event['hook_event_name'] == 'PreToolUse' and out != {} and 'infrastructure' in json.dumps(out))
    out, ms, code = send(state, stop)
    times.append(ms)
    return out, times, errors + (code != 0)


def main():
    plants = twins = controls = caught = admitted_twin = admitted_control = errors = 0
    misses, falses, times, blocked_bytes = [], [], [], []
    for users in range(1, 13):
        out, t, e = play(users, {users - 1}, f'p{users}')       # plant D: the last use file never read
        plants += 1; errors += e; times += t
        text = out.get('reason', '')
        if 'rule f' in text and f'u{users - 1}.py' in text:
            caught += 1; blocked_bytes.append(len(text.encode()))
        else:
            misses.append(f'D with {users} users: {text[:120] or "admitted"}')
        out, t, e = play(users, set(), f't{users}')              # twin: everything read
        twins += 1; errors += e; times += t
        if out == {}:
            admitted_twin += 1
        else:
            falses.append(f'twin with {users} users: {json.dumps(out)[:120]}')
    for k in range(12):                                          # control: nothing uses the name
        out, t, e = play(0, set(), f'c{k}')
        controls += 1; errors += e; times += t
        if out == {}:
            admitted_control += 1
        else:
            falses.append(f'control {k}: {json.dumps(out)[:120]}')
    result = {'plugin': str(PLUGIN), 'plant_D_caught': [caught, plants], 'twin_admitted': [admitted_twin, twins],
              'no_use_admitted': [admitted_control, controls], 'errors': errors, 'misses': misses, 'false_holds': falses,
              'ms_per_hook_median': round(statistics.median(times), 1), 'hook_calls': len(times),
              'rule_f_hold_bytes_median': statistics.median(blocked_bytes) if blocked_bytes else 0}
    print(json.dumps(result, indent=1))
    print('plant D caught', show(caught, plants)); print('twin admitted', show(admitted_twin, twins))
    print('no-use admitted', show(admitted_control, controls))
    if '--json' in sys.argv:
        Path(sys.argv[sys.argv.index('--json') + 1]).write_text(json.dumps(result, indent=1))


main()
