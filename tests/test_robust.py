"""Makoto holds without exception: an infrastructure error blocks, names the error and the one way to
disable Makoto; a decided hold blocks everywhere and every time; hooks are timed, the lock is capped,
and each call reads only what is new since the last."""
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


DISABLE = 'claude plugin disable makoto'


def message(response):
    return response.get('reason') or response.get('hookSpecificOutput', {}).get('permissionDecisionReason', '')


def failure(response):
    return denied(response) and 'makoto infrastructure error' in message(response)


def way_out(response):
    return DISABLE in message(response)


def journal(tmp):
    return tmp / 'state' / (hashlib.sha256(b'plant').hexdigest() + '.jsonl')


# 1. Fail closed on every infrastructure error; the block names the error and the way out.

def test_unwritable_state_blocks_and_names_the_error(tmp_path):
    state = tmp_path / 'state'
    state.write_text('a file where the state folder should be')
    response = raw_send(state, WRITE_STEP)
    assert failure(response) and way_out(response)
    assert any(name in message(response) for name in ('NotADirectoryError', 'FileExistsError'))


def test_malformed_host_event_blocks(tmp_path):
    response = raw_send(tmp_path / 'state', ev('PreToolUse', tool_name='Write', tool_input={'file_path': 'x'}))
    assert failure(response) and way_out(response)


def corrupt(tmp):
    path = journal(tmp)
    path.write_text(path.read_text().replace('source data', 'tampered!!!', 1))
    (tmp / 'state' / (path.name + '.ckpt')).unlink(missing_ok=True)
    return path


def test_corrupted_journal_is_set_aside_and_only_the_missing_reading_blocks(tmp_path):
    for event in read('source data'):
        send(tmp_path, event)
    path = corrupt(tmp_path)
    # The step that needed the destroyed reading is held for the reading, not for the error.
    held = send(tmp_path, dict(WRITE_STEP, tool_use_id='one'))
    assert denied(held) and not failure(held) and held['hookSpecificOutput']['permissionDecisionReason'].startswith('makoto rule a ')
    # The corrupted journal is kept beside a fresh one.
    kept = sorted(path.parent.glob(path.name + '.corrupt-*'))
    assert len(kept) == 1 and 'tampered!!!' in kept[0].read_text()
    assert path.exists() and 'tampered!!!' not in path.read_text()
    # Once the reading is made again the same step is admitted: nothing else stays blocked.
    for event in read('source data', 'again'):
        assert send(tmp_path, event) == {}
    assert send(tmp_path, dict(WRITE_STEP, tool_use_id='two')) == {}


def test_corrupted_journal_does_not_block_a_step_that_needs_no_reading(tmp_path):
    for event in read('source data'):
        send(tmp_path, event)
    corrupt(tmp_path)
    assert send(tmp_path, ev('PostToolUse', tool_name='Read', tool_use_id='x', tool_input={'file_path': 'a'}, tool_response={'content': 'z'})) == {}


def test_user_prompt_submit_is_never_blocked(tmp_path):
    state = tmp_path / 'state'
    state.write_text('a file where the state folder should be')
    assert raw_send(state, ev('UserPromptSubmit', prompt='hello')) == {}
    assert failure(raw_send(state, WRITE_STEP))  # the same error still blocks a step


def test_user_prompt_submit_after_a_corrupted_journal_is_admitted_and_recorded(tmp_path):
    for event in read('source data'):
        send(tmp_path, event)
    corrupt(tmp_path)
    assert send(tmp_path, ev('UserPromptSubmit', prompt='next turn')) == {}
    rows = [json.loads(line) for line in journal(tmp_path).read_text().splitlines()]
    assert [r['event']['hook_event_name'] for r in rows] == ['UserPromptSubmit']


def test_unreadable_event_input_blocks(tmp_path):
    command = HOOKS['Stop'][0]['hooks'][0]['command']
    env = {k: v for k, v in os.environ.items() if not k.startswith('MAKOTO_')}
    env.update(CLAUDE_PLUGIN_ROOT=str(PLUGIN), MAKOTO_STATE_DIR=str(tmp_path / 'state'), PYTHONDONTWRITEBYTECODE='1')
    run = subprocess.run(['bash', '-c', command], input='not json', env=env, capture_output=True, text=True, timeout=60)
    response = json.loads(run.stdout)
    assert denied(response) and way_out(response)


def test_rule_findings_still_deny(tmp_path):
    plant, _ = CASES['a']
    for event in plant[:-1]:
        send(tmp_path, event)
    assert send(tmp_path, plant[-1])['decision'] == 'block'


# 2. A timeout on every hook and a capped session lock; a busy lock blocks.

def test_every_hook_has_a_timeout():
    for name, groups in HOOKS.items():
        for group in groups:
            for hook in group['hooks']:
                assert isinstance(hook.get('timeout'), int) and 0 < hook['timeout'] <= 30, name


def test_held_lock_blocks_within_its_cap(tmp_path):
    state = tmp_path / 'state'
    state.mkdir()
    lock = state / (hashlib.sha256(b'plant').hexdigest() + '.jsonl.lock')
    with open(lock, 'a+b') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        start = time.monotonic()
        response = raw_send(state, WRITE_STEP, timeout=20, MAKOTO_LOCK_SECONDS='0.5')
        assert time.monotonic() - start < 10
    assert failure(response) and 'session lock busy' in message(response)


# 3. A decided hold blocks every time and everywhere; nothing caps or scopes it.

def test_active_stop_is_held_every_time(tmp_path):
    plant, _ = CASES['a']
    for event in plant[:-1]:
        send(tmp_path, event)
    for _ in range(3):
        response = send(tmp_path, plant[-1])
        assert response['decision'] == 'block' and response['reason'].startswith('makoto rule a ')
    rows = [json.loads(line) for line in journal(tmp_path).read_text().splitlines()]
    assert rows[-1]['findings'] and 'stop_cap' not in rows[-1]


def test_hold_outside_the_old_block_in_scope_still_blocks(tmp_path):
    plant, _ = CASES['a']
    for event in plant[:-1]:
        send(tmp_path, event)
    outside = dict(plant[-1], cwd='/somewhere/else')
    response = raw_send(tmp_path / 'state', outside, MAKOTO_BLOCK_IN='/w')
    assert response['decision'] == 'block' and 'report only' not in json.dumps(response)


def test_readme_names_the_one_way_to_disable_and_no_removed_switch():
    readme = (PLUGIN.parent / 'README.md').read_text(encoding='utf-8')
    assert DISABLE in readme
    assert 'MAKOTO_BLOCK_IN' not in readme and 'stop_cap' not in readme


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
