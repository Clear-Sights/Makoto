"""Every hold names the one Immediacy rule it enforces, states the missing reading and asks no question."""
import pytest

from test_rules import CASES, RUN, call, ev, read, send

ENFORCES = {'a': 'Original: Read the original instead of a derivation.',
            'b': 'Original: Read the original instead of a derivation.',
            'c': 'Original: Read the original instead of a derivation.',
            'd': 'Unchanged: Do not assume what can change has not.'}


@pytest.mark.parametrize('rule', sorted(CASES))
def test_hold_names_its_rule_and_the_missing_reading(tmp_path, rule):
    plant = CASES[rule][0]
    for event in plant[:-1]:
        send(tmp_path, event)
    reason = send(tmp_path, plant[-1])['reason']
    assert reason.startswith('makoto rule ' + rule + ' ')
    assert ENFORCES[rule] in reason
    other = [text for key, text in ENFORCES.items() if text != ENFORCES[rule]][0]
    assert other not in reason, 'a hold names the one rule it enforces'
    assert ' Missing: ' in reason
    assert '?' not in reason


def test_makoto_speaks_only_when_it_holds(tmp_path):
    for event in read('source data'):
        assert send(tmp_path, event) == {}
    write = ev('PreToolUse', tool_name='Write', tool_use_id='step', tool_input={'file_path': 'out.txt', 'content': 'source data'})
    assert send(tmp_path, write) == {}
    # A first Stop that no rule holds is admitted without a block or any text.
    assert send(tmp_path, ev('Stop', last_assistant_message='source data')) == {}


# The one action each hold names, and the events that perform it.
CLEARS = {
    'a': ('Clear: Read the original artifact this step relies on.', read('source data', 'fix')),
    'b': ('Clear: Read a source that contains these exact characters.', read('source data unread_subject', 'fix')),
    'c': ('Clear: Fetch this exact subject with WebFetch or WebSearch in this turn.',
          call('WebFetch', {'url': 'https://example.test/a'}, {'content': 'https://example.test/a'}, 'fix')),
    'd': ('Clear: Run it and read its output.', RUN),
}


@pytest.mark.parametrize('rule', sorted(CASES))
def test_the_named_action_clears_the_hold(tmp_path, rule):
    plant = CASES[rule][0]
    for event in plant[:-1]:
        send(tmp_path, event)
    held = send(tmp_path, plant[-1])
    action, events = CLEARS[rule]
    assert held['reason'].count('Clear: ') == 1 and action in held['reason']
    for event in events:
        assert send(tmp_path, event) == {}
    assert send(tmp_path, plant[-1]) == {}, 'the named action must clear the hold'
