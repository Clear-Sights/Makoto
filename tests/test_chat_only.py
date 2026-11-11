"""Rule a does not hold the final answer of a session that made no tool call; every other hold stays."""
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
}
UNSEEN = ('Which port does the service use?', 'config/app.json sets port to 8080.')
NEW_MODULE = {'file_path': 'new.py', 'content': 'x = 1\n'}
TEXT_FILE = {'file_path': 'out.txt', 'content': 'source data'}
# A session whose only tool call is a Write: (its events, whether the Write itself is held).
WRITE_ONLY = {
    'admitted': (call('Write', NEW_MODULE, {'content': 'ok'}, 'w'), False),  # a new module needs no reading
    'refused': ([ev('PreToolUse', tool_name='Write', tool_use_id='w', tool_input=TEXT_FILE)], True),
}


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


def test_a_tool_less_write_is_still_held_by_rule_a(tmp_path):
    response = send(tmp_path, ev('PreToolUse', tool_name='Write', tool_use_id='w', tool_input=TEXT_FILE))
    assert held(response) and 'a' in rules(response)


@pytest.mark.parametrize('case', sorted(WRITE_ONLY))
def test_a_session_whose_only_tool_call_is_a_write_still_holds_its_final_answer_by_rule_a(tmp_path, case):
    events, write_held = WRITE_ONLY[case]
    assert [held(send(tmp_path, event)) for event in events] == [write_held] + [False] * (len(events) - 1)
    response = send(tmp_path, final('Done.'))
    assert held(response) and 'a' in rules(response)


def test_a_tool_less_answer_naming_an_unseen_path_is_still_held_by_rule_b(tmp_path):
    prompt, answer = UNSEEN
    assert send(tmp_path, ev('UserPromptSubmit', prompt=prompt)) == {}
    response = send(tmp_path, final(answer))
    assert held(response) and 'b' in rules(response)


SESSIONS = {form: ([ev('UserPromptSubmit', prompt=prompt)], answer) for form, (prompt, answer) in CHAT.items()}
SESSIONS['unseen path'] = ([ev('UserPromptSubmit', prompt=UNSEEN[0])], UNSEEN[1])
SESSIONS.update(('write ' + case, (events, 'Done.')) for case, (events, _) in WRITE_ONLY.items())


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
