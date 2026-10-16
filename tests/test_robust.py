"""Makoto never wedges a session: infrastructure errors admit, hooks are timed, the lock is capped,
an active Stop is held at most once more, and each call reads only what is new since the last."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from test_rules import CASES, HOOKS, PLUGIN, ev, read, send, stop

WRITE_STEP = ev('PreToolUse', tool_name='Write', tool_use_id='step', tool_input={'file_path': 'out.txt', 'content': 'source data'})


def raw_send(state, event, timeout=60, **env_extra):
    command = HOOKS[event['hook_event_name']][0]['hooks'][0]['command']
    env = {k: v for k, v in os.environ.items() if not k.startswith('MAKOTO_')}
    env.update(CLAUDE_PLUGIN_ROOT=str(PLUGIN), MAKOTO_STATE_DIR=str(state), PYTHONDONTWRITEBYTECODE='1', **env_extra)
    run = subprocess.run(['bash', '-c', command], input=json.dumps(event), env=env,
                         capture_output=True, text=True, timeout=timeout)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def denied(response):
    return (response.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'
            or response.get('decision') == 'block')


def failure(response):
    return 'infrastructure' in response.get('systemMessage', '')


def journal(tmp):
    return tmp / 'state' / (hashlib.sha256(b'plant').hexdigest() + '.jsonl')


# 1. Fail open on every infrastructure error; deny only on rule findings.

def test_unwritable_state_admits_with_a_message(tmp_path):
    state = tmp_path / 'state'
    state.write_text('a file where the state folder should be')
    response = raw_send(state, WRITE_STEP)
    assert not denied(response) and failure(response)


def test_malformed_host_event_admits(tmp_path):
    response = raw_send(tmp_path / 'state', ev('PreToolUse', tool_name='Write', tool_input={'file_path': 'x'}))
    assert not denied(response) and failure(response)


def test_corrupted_journal_never_denies_the_rest_of_the_session(tmp_path):
    for event in read('source data'):
        send(tmp_path, event)
    path = journal(tmp_path)
    path.write_text(path.read_text().replace('source data', 'tampered!!!', 1))
    (tmp_path / 'state' / (path.name + '.ckpt')).unlink(missing_ok=True)
    for tid in ('one', 'two'):
        response = send(tmp_path, dict(WRITE_STEP, tool_use_id=tid))
        assert not denied(response)


def test_rule_findings_still_deny(tmp_path):
    plant, _ = CASES['a']
    assert send(tmp_path, plant[-1])['decision'] == 'block'


# 2. A timeout on every hook and a capped, non-blocking session lock.

def test_every_hook_has_a_timeout():
    for name, groups in HOOKS.items():
        for group in groups:
            for hook in group['hooks']:
                assert isinstance(hook.get('timeout'), int) and 0 < hook['timeout'] <= 30, name


def test_held_lock_admits_within_its_cap(tmp_path):
    state = tmp_path / 'state'
    state.mkdir()
    lock = state / (hashlib.sha256(b'plant').hexdigest() + '.jsonl.lock')
    with open(lock, 'a+b') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        start = time.monotonic()
        response = raw_send(state, WRITE_STEP, timeout=20, MAKOTO_LOCK_SECONDS='0.5')
        assert time.monotonic() - start < 10
    assert not denied(response) and failure(response)


# 3. An active Stop is held at most once more per turn.

def test_active_stop_is_held_once_then_admitted(tmp_path):
    plant, _ = CASES['a']
    assert send(tmp_path, plant[-1])['decision'] == 'block'
    second = send(tmp_path, plant[-1])
    assert not denied(second) and 'makoto rule a' in second['systemMessage']
    rows = [json.loads(line) for line in journal(tmp_path).read_text().splitlines()]
    assert rows[-1]['findings'] and rows[-1]['stop_cap']
    send(tmp_path, ev('UserPromptSubmit', prompt='next turn'))
    assert send(tmp_path, plant[-1])['decision'] == 'block'


# 4. Incremental replay: same decisions, and only new bytes are read.

def transcript_lines(n):
    rows = [{'type': 'user', 'message': {'role': 'user', 'content': 'please summarise source.txt'}}]
    for i in range(n):
        tid = 't%d' % i
        rows.append({'type': 'assistant', 'message': {'role': 'assistant', 'content': [
            {'type': 'tool_use', 'id': tid, 'name': 'Read', 'input': {'file_path': 'f%d.txt' % i}}]}})
        rows.append({'type': 'user', 'message': {'role': 'user', 'content': [
            {'type': 'tool_result', 'tool_use_id': tid, 'content': 'value_%d data' % i}]}})
    return [json.dumps(r) + '\n' for r in rows]


def scenario(tmp, **env):
    """Every case of test_rules plus a transcript-fed session; returns every response in order."""
    out = []
    for rule in sorted(CASES):
        for name, events in zip(('plant', 'twin'), CASES[rule]):
            state = tmp / rule / name
            out += [raw_send(state, e, **env) for e in events]
    path = tmp / 'transcript.jsonl'
    lines = transcript_lines(6)
    for i in range(1, len(lines) + 1):
        path.write_text(''.join(lines[:i]))
        step = ev('PreToolUse', tool_name='Write', tool_use_id='w%d' % i, transcript_path=str(path),
                  tool_input={'file_path': 'o.txt', 'content': 'value_%d data' % (i // 2)})
        out.append(raw_send(tmp / 'transcript-state', step, **env))
        out.append(raw_send(tmp / 'transcript-state', ev('Stop', transcript_path=str(path),
                                                           last_assistant_message='value_%d' % (i // 2)), **env))
    return out


def test_checkpoint_gives_the_same_decisions_as_full_replay(tmp_path):
    assert scenario(tmp_path / 'full', MAKOTO_CHECKPOINT='0') == scenario(tmp_path / 'incremental')


def test_only_new_transcript_bytes_are_read(tmp_path):
    path = tmp_path / 'transcript.jsonl'
    big = json.dumps({'type': 'user', 'message': {'role': 'user', 'content': 'p' * 5000}}) + '\n'
    lines = [big] + transcript_lines(3)[1:]
    path.write_text(''.join(lines))
    state = tmp_path / 'state'
    step = dict(WRITE_STEP, transcript_path=str(path), tool_use_id='a')
    first = raw_send(state, step)
    assert not failure(first)
    # Blank out an already-read line past the first 4 KB in place; a full re-read would fail to parse it.
    more = transcript_lines(4)[-2:]
    path.write_text(big + ' ' * (len(lines[1]) - 1) + '\n' + ''.join(lines[2:]) + ''.join(more))
    second = raw_send(state, dict(step, tool_use_id='b'))
    assert not failure(second)
    full = raw_send(state, dict(step, tool_use_id='c'), MAKOTO_CHECKPOINT='0')
    assert failure(full)


def test_checkpoint_follows_a_changed_cwd(tmp_path):
    # A transcript row without its own cwd takes the candidate's; a new cwd must not reuse the old replay.
    path = tmp_path / 'transcript.jsonl'
    write = {'type': 'assistant', 'message': {'role': 'assistant', 'content': [
        {'type': 'tool_use', 'id': 'w', 'name': 'Write', 'input': {'file_path': 'a.py', 'content': 'print(1)\n'}}]}}
    path.write_text(json.dumps(write) + '\n')
    outs = {}
    for mode in ('0', '1'):
        state = tmp_path / ('state' + mode)
        for cwd in ('/a', '/b'):
            step = dict(ev('Stop', transcript_path=str(path), last_assistant_message='Done'), cwd=cwd)
            outs.setdefault(mode, []).append(raw_send(state, step, MAKOTO_CHECKPOINT=mode))
    assert outs['0'] == outs['1']
    ckpt = (tmp_path / 'state1' / (hashlib.sha256(b'plant').hexdigest() + '.jsonl.ckpt')).read_bytes()
    assert b'/b/a.py' in ckpt and b'/a/a.py' not in ckpt


def test_replaced_transcript_is_read_from_its_start(tmp_path):
    path = tmp_path / 'transcript.jsonl'
    state = tmp_path / 'state'
    path.write_text(''.join(transcript_lines(2)))
    raw_send(state, dict(WRITE_STEP, transcript_path=str(path), tool_use_id='a'))
    # Same session, rewritten (compacted) to a longer file: an offset into the old one is mid-line here.
    path.write_text(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': 'x' * 37}}) + '\n' + ''.join(transcript_lines(3)))
    response = raw_send(state, dict(WRITE_STEP, transcript_path=str(path), tool_use_id='b'))
    assert not failure(response)
    assert response == raw_send(state, dict(WRITE_STEP, transcript_path=str(path), tool_use_id='c'), MAKOTO_CHECKPOINT='0')
