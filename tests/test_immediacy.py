"""Every hold names the one Immediacy rule it enforces, states the missing reading and asks no question."""
import pytest

from test_rules import CASES, ev, read, send

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
