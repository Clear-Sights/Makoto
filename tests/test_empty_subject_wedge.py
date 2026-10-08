"""Empty shell operands must not poison current calls or transcript replay."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin'))
from makoto2 import hook


@pytest.fixture(params=['grep -c "" a.txt', 'python3 ""', 'cat ""', 'echo hi > ""'])
def empty_call(request, tmp_path):
    command = request.param
    transcript = tmp_path / 'transcript.jsonl'
    config = {'state_dir': str(tmp_path / 'state'), 'adapter': 'inferred'}
    rows = [
        {'type': 'user', 'sessionId': 's', 'message': {'role': 'user', 'content': 'go'}},
        {'type': 'assistant', 'sessionId': 's', 'message': {'role': 'assistant', 'content': [
            {'type': 'tool_use', 'id': 't1', 'name': 'Bash', 'input': {'command': command}}]}},
    ]

    def write():
        transcript.write_text(''.join(json.dumps(row) + '\n' for row in rows))

    def send(tool, tid, ti):
        return hook.main(json.dumps(dict(hook_event_name='PreToolUse', session_id='s',
                         cwd='/w', transcript_path=str(transcript), tool_name=tool,
                         tool_use_id=tid, tool_input=ti)), config)

    write()
    initial = send('Bash', 't1', {'command': command})
    rows.extend([
        {'type': 'user', 'sessionId': 's', 'message': {'role': 'user', 'content': [
            {'type': 'tool_result', 'tool_use_id': 't1', 'content': 'hook denied', 'is_error': True}]}},
        {'type': 'assistant', 'sessionId': 's', 'message': {'role': 'assistant', 'content': [
            {'type': 'tool_use', 'id': 't2', 'name': 'mcp__hearthbot__reply', 'input': {'text': 'hi'}}]}},
    ])
    write()
    return initial, send('mcp__hearthbot__reply', 't2', {'text': 'hi'})


def test_later_reply_is_admitted(empty_call):
    assert empty_call[1] == {}


def test_empty_operand_has_no_transport_failure(empty_call):
    assert 'transport/contract failure' not in json.dumps(empty_call[0])


def test_failed_replay_is_unknown_without_partial_evidence(tmp_path):
    transcript = tmp_path / 'history.jsonl'
    bad = dict(hook_event_name='PreToolUse', session_id='s', cwd='/w',
               tool_name='Read', tool_use_id='bad', tool_input={'file_path': 'a.txt'},
               makoto={'reads': [{'subject': ''}]})
    post = dict(bad, hook_event_name='PostToolUse', tool_response={'content': 'secret_evidence'})
    good = dict(hook_event_name='UserPromptSubmit', session_id='s', prompt='go')
    transcript.write_text(''.join(json.dumps(row) + '\n' for row in (bad, post, good)))
    config = {'state_dir': str(tmp_path / 'state'), 'adapter': 'inferred'}
    candidate = dict(hook_event_name='PreToolUse', session_id='s', cwd='/w',
                     transcript_path=str(transcript), tool_name='mcp__hearthbot__reply',
                     tool_use_id='reply', tool_input={'text': 'hi'})
    assert hook.main(json.dumps(candidate), config) == {}
    row = hook.sigma_read(hook.sigma_path(config['state_dir'], 's'), 's')[-1]
    assert row['unknown'][0]['reason'].startswith('historical ingest failed:')
    assert row['unknown'][1]['reason'] == 'unpaired, replayed or mismatched tool result'
    assert row['turn_id'] == '3'
    # The same malformed record as the current event must still fail closed.
    assert 'transport/contract failure' in json.dumps(hook.main(json.dumps(bad), config))
