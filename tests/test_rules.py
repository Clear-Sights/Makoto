"""Each of rules a-d holds its plant and admits its twin, through the exact hooks.json command."""
import json
import os
from pathlib import Path
import subprocess

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / 'plugin'
HOOKS = json.loads((PLUGIN / 'hooks' / 'hooks.json').read_text(encoding='utf-8'))['hooks']
QUESTIONS = ("Before this step: (1) If it relies on a definition, did you read the thing itself against that definition? "
             "(2) If it carries a result to another place or time, did you read the same thing again where and when it lands? "
             "(3) If it says how a branch behaves, did you feed that branch an input and read its response? "
             "(4) Is it based on the original source, read this turn, rather than on an earlier answer?")


def send(tmp, event):
    """One event through the command hooks.json registers for it."""
    command = HOOKS[event['hook_event_name']][0]['hooks'][0]['command']
    env = {k: v for k, v in os.environ.items() if not k.startswith('MAKOTO_')}
    env.update(CLAUDE_PLUGIN_ROOT=str(PLUGIN), MAKOTO_STATE_DIR=str(tmp / 'state'), PYTHONDONTWRITEBYTECODE='1')
    run = subprocess.run(['bash', '-c', command], input=json.dumps(event), env=env,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def ev(name, **fields):
    return dict(hook_event_name=name, session_id='plant', cwd='/w', **fields)


def call(tool, tool_input, response, tid):
    return [ev('PreToolUse', tool_name=tool, tool_use_id=tid, tool_input=tool_input),
            ev('PostToolUse', tool_name=tool, tool_use_id=tid, tool_input=tool_input, tool_response=response)]


def read(text, tid='read'):
    return call('Read', {'file_path': 'source.txt'}, {'content': text}, tid)


def stop(text):
    # An active Stop: an admitted one answers {} (the questions were shown once already).
    return ev('Stop', last_assistant_message=text, stop_hook_active=True)


ADMITTED = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'additionalContext': QUESTIONS}}
WRITE = read('print(731)\n', 'spec') + call('Write', {'file_path': 'run.py', 'content': 'print(731)\n'}, {'content': 'ok'}, 'write')
RUN = call('Bash', {'command': 'python3 run.py'}, {'stdout': '731\n', 'exitCode': 0}, 'run')

CASES = {
    # rule: (plant events, twin events); the last event of each is the step under test.
    'a': ([stop('source data')],
          read('source data') + [stop('source data')]),
    'b': (read('source data') + [stop('unread_subject')],
          read('source data unread_subject') + [stop('unread_subject')]),
    'c': (read('https://example.test/a') + [stop('https://example.test/a')],
          call('WebFetch', {'url': 'https://example.test/a'}, {'content': 'https://example.test/a'}, 'fetch')
          + [stop('https://example.test/a')]),
    'd': (WRITE + [stop('Done')],
          WRITE + RUN + [stop('Done')]),
}


@pytest.mark.parametrize('rule', sorted(CASES))
def test_rule_holds_plant_and_admits_twin(tmp_path, rule):
    plant, twin = CASES[rule]
    for name, events in (('plant', plant), ('twin', twin)):
        tmp = tmp_path / name
        for event in events[:-1]:
            assert send(tmp, event) in ({}, ADMITTED)
        response = send(tmp, events[-1])
        if name == 'plant':
            assert response.get('decision') == 'block'
            assert response['reason'].startswith('makoto rule ' + rule + ' ')
        else:
            assert response == {}


def test_admitted_write_carries_the_four_questions(tmp_path):
    for event in read('source data'):
        send(tmp_path, event)
    step = ev('PreToolUse', tool_name='Write', tool_use_id='step', tool_input={'file_path': 'out.txt', 'content': 'source data'})
    assert send(tmp_path, step) == ADMITTED
