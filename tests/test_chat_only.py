"""A final answer of a session that made no tool call is admitted whatever it says; rule d still holds an unrun edit."""
import re

import pytest

from test_rules import call, ev, send

# A tool-less session: the user's prompt, then the final answer.
CHAT = {
    'capital': ('What is the capital of France?', 'Paris is the capital of France.'),
    'arithmetic': ('What is 17 times 23?', '391'),
    'greeting': ('hi', 'Hello! How can I help?'),
    'code concept': ('How does a Python list differ from a tuple?', 'A list is mutable and a tuple is not.'),
    'tests pass': ('Do the tests pass?', 'Yes, all tests pass.'),
    'unread names': ('Which port does the service use?', 'config/app.json sets port to 8080 (see https://example.test/a).'),
}
NEW_MODULE = {'file_path': 'new.py', 'content': 'x = 1\n'}


def final(text, name='Stop'):
    return ev(name, last_assistant_message=text, stop_hook_active=False)


def held(response):
    return (response.get('decision') == 'block'
            or response.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny')


def rules(response):
    text = response.get('reason') or response.get('hookSpecificOutput', {}).get('permissionDecisionReason', '')
    return sorted(set(re.findall(r'makoto rule (\w) \[', text)))


@pytest.mark.parametrize('form', sorted(CHAT))
def test_a_tool_less_final_answer_is_admitted(tmp_path, form):
    prompt, answer = CHAT[form]
    assert send(tmp_path, ev('UserPromptSubmit', prompt=prompt)) == {}
    assert send(tmp_path, final(answer)) == {}


def test_a_session_whose_only_tool_call_is_a_code_write_holds_its_final_answer_by_rule_d(tmp_path):
    assert [held(send(tmp_path, event)) for event in call('Write', NEW_MODULE, {'content': 'ok'}, 'w')] == [False, False]
    response = send(tmp_path, final('Done.'))
    assert held(response) and rules(response) == ['d']


SESSIONS = {form: ([ev('UserPromptSubmit', prompt=prompt)], answer) for form, (prompt, answer) in CHAT.items()}
SESSIONS['write'] = (call('Write', NEW_MODULE, {'content': 'ok'}, 'w'), 'Done.')


@pytest.mark.parametrize('case', sorted(SESSIONS))
def test_a_subagent_stop_is_decided_as_a_stop_is(tmp_path, case):
    events, answer = SESSIONS[case]
    decided = {}
    for name in ('Stop', 'SubagentStop'):
        tmp = tmp_path / name
        for event in events:
            send(tmp, event)
        response = send(tmp, final(answer, name))
        decided[name] = (held(response), rules(response))
    assert decided['Stop'] == decided['SubagentStop']
