"""Step 5: run responses are readings; four questions precede admitted steps."""
import subprocess

import pytest

from test_shapes import Session, event, pair, output
from makoto2.hook import FOUR_QUESTIONS
from run_pairs import held


EXPECTED = "Before this step: (1) If it relies on a definition, did you read the thing itself against that definition? (2) If it carries a result to another place or time, did you read the same thing again where and when it lands? (3) If it says how a branch behaves, did you feed that branch an input and read its response? (4) Is it based on the original source, read this turn, rather than on an earlier answer?"


@pytest.mark.parametrize('command', ['echo 731', "printf '731\\n'", 'python3 -c "print(731)"', 'touch out.txt; echo 731'])
def test_answer_after_command_printed_output_is_not_held(tmp_path, command):
    result = subprocess.run(['bash', '-c', command], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert result.stdout == '731\n'
    s = Session(tmp_path)
    s.feed(pair('Bash', {'command': command}, result.stdout))
    assert not held(s.send(output('731')))
    assert s.rules() == set()


def test_run_status_is_response_even_without_printed_text(tmp_path):
    s = Session(tmp_path)
    s.feed(pair('Bash', {'command': 'touch out.txt'}, ''))
    assert not held(s.send(output('Done')))


@pytest.mark.parametrize('tool,ti', [
    ('Execute', {'code': 'print(731)'}),
    ('Query', {'query': 'select 731'}),
    ('Request', {'request': 'read value'}),
])
def test_other_tool_run_query_request_response_is_reading(tmp_path, tool, ti):
    s = Session(tmp_path)
    s.feed(pair(tool, ti, '731'))
    assert not held(s.send(output('731')))


@pytest.mark.parametrize('tool,ti', [
    ('Read', {'file_path': 'out.txt'}),
    ('Bash', {'command': 'cat out.txt'}),
])
def test_only_reading_session_written_file_is_held(tmp_path, tool, ti):
    # Native transcript can contain writes executed before this hook was installed.
    write = output('731', 'Write')
    rows = [write, dict(write, hook_event_name='PostToolUse', tool_response={'content': 'ok'})]
    rows += pair(tool, ti, '731', tid='own')
    import json
    transcript = tmp_path / 'transcript.jsonl'
    transcript.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    s = Session(tmp_path)
    for active in (False, True, True):
        response = s.send(dict(output('731'), transcript_path=str(transcript), stop_hook_active=active))
        assert held(response)
        assert s.rules() == {'a'}
        assert FOUR_QUESTIONS not in str(response)


@pytest.mark.parametrize('boundary', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'commit', 'push'])
def test_questions_on_every_admitted_pretool_step(tmp_path, boundary):
    assert FOUR_QUESTIONS == EXPECTED
    s = Session(tmp_path)
    s.send(event('UserPromptSubmit', prompt='out.txt git commit push -m'))
    s.feed(pair())
    for i in range(2):
        response = s.send(output(boundary=boundary, tid=f'step-{i}'))
        assert not held(response)
        assert response == {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'additionalContext': EXPECTED}}


@pytest.mark.parametrize('boundary', ['Stop', 'SubagentStop', 'PreDelivery'])
def test_questions_once_at_stop_and_again_next_turn(tmp_path, boundary):
    s = Session(tmp_path)
    s.feed(pair())
    for turn in range(2):
        for active in (False, True, True):
            response = s.send(dict(output(boundary=boundary), stop_hook_active=active))
            assert response == ({} if active else {'decision': 'block', 'reason': EXPECTED})
            assert s.journal()[-1]['admitted']
            assert s.rules() == set()
        s.send(event('UserPromptSubmit', prompt='next turn'))


@pytest.mark.parametrize('text,rule', [('source data', 'a'), ('unread_subject', 'b'), ('https://example.test/a', 'c')])
@pytest.mark.parametrize('boundary', ['Write', 'Stop'])
def test_rule_holds_take_precedence_over_questions(tmp_path, text, rule, boundary):
    s = Session(tmp_path)
    if rule != 'a':
        s.feed(pair(text=text if rule == 'c' else 'source data'))
    for active in (False, True, True):
        response = s.send(dict(output(text, boundary), stop_hook_active=active))
        assert held(response)
        assert rule in s.rules()
        assert FOUR_QUESTIONS not in str(response)
        assert not s.journal()[-1]['admitted']


def test_non_dependent_steps_have_no_questions(tmp_path):
    s = Session(tmp_path)
    assert s.send(event('UserPromptSubmit', prompt='read the source')) == {}
    for ev in pair():
        assert s.send(ev) == {}
    for ev in pair('Bash', {'command': 'echo 731'}, '731', tid='run'):
        assert s.send(ev) == {}
