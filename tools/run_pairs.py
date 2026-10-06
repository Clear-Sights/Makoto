#!/usr/bin/env python3
"""Replay supplied native sessions; never execute commands or inspect subjects.

Input: {"sessions": [{"id": "x", "files": {"relative/path": "bytes"},
                     "events": [native_hook_event, ...], "step_index": 3}]}
A top-level session list is also accepted. step_index is zero-based in events.
Output: one JSON object per session, including held and the actual hook response.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

PLUGIN = Path(__file__).resolve().parents[1] / 'plugin'


def invoke(event, state_dir, adapter):
    env = dict(os.environ, MAKOTO_STATE_DIR=str(state_dir), MAKOTO_ADAPTER=adapter,
               PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONPATH', None)
    return json.loads(subprocess.run([sys.executable, '-m', 'makoto2'], cwd=PLUGIN,
                     env=env, input=json.dumps(event), capture_output=True,
                     text=True, check=True).stdout)


def held(response):
    return response.get('decision') == 'block' or response.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'


def drive_session(session, adapter):
    events = session['events']
    index = session['step_index']
    if type(index) is not int or not 0 <= index < len(events):
        raise ValueError('step_index must name an event')
    with tempfile.TemporaryDirectory(prefix='makoto-pairs-') as directory:
        base = Path(directory)
        cwd = base / 'workspace'
        cwd.mkdir()
        for name, content in session.get('files', {}).items():
            target = cwd / name
            if target.is_absolute() and cwd.resolve() not in target.resolve().parents:
                raise ValueError('session files must stay in temporary cwd')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        responses = []
        for original in events:
            event = copy.deepcopy(original)
            event.setdefault('session_id', str(session.get('id', 'session')))
            # Recorded identities are never opened. Relative paths bind to the
            # isolated cwd; explicit typed authorities remain as supplied.
            event['cwd'] = str(cwd)
            responses.append(invoke(event, base / 'state', adapter))
        return {'session': session.get('id', events[index].get('session_id', 'session')),
                'step_index': index, 'held': held(responses[index]),
                'response': responses[index]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pairs', type=Path)
    parser.add_argument('--adapter', default='inferred', choices=('inferred',))
    options = parser.parse_args()
    data = json.loads(options.pairs.read_text(encoding='utf-8'))
    sessions = data if isinstance(data, list) else data.get('sessions', [data] if 'events' in data else [])
    if not sessions:
        raise ValueError('no sessions supplied')
    for session in sessions:
        print(json.dumps(drive_session(session, options.adapter), ensure_ascii=False))


if __name__ == '__main__':
    main()
