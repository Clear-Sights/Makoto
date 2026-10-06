"""Self-authored witness plants from SHAPES.md; no external pair corpus."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'plugin'), str(ROOT / 'tools')]
from makoto2 import hook
from run_pairs import invoke, held, drive_session


def event(name, **fields):
    return dict(hook_event_name=name, session_id='plant', cwd='/w', **fields)


def read_pair(subject='source', tid='r', text='original', place=None, tool='Read', selector=None, **receipt):
    ti = {'file_path': subject}
    if tool == 'Bash':
        ti = {'command': 'probe --input z'}
    elif tool == 'WebFetch':
        ti = {'url': subject, 'prompt': 'body'}
    elif tool == 'Grep':
        ti = {'path': subject, 'pattern': 'z'}
    pre_meta = {'place': place} if place else {}
    post_meta = dict(pre_meta)
    if receipt or selector:
        post_meta['reads'] = [dict(subject=subject, selector=selector or 'content', complete=True, **receipt)]
    response = {'stdout': text, 'stderr': '', 'exitCode': 1} if tool == 'Bash' else {'content': text}
    return [event('PreToolUse', tool_use_id=tid, tool_name=tool, tool_input=ti, makoto=pre_meta),
            event('PostToolUse', tool_use_id=tid, tool_name=tool, tool_input=ti, tool_response=response, makoto=post_meta)]


def output(basis='source=source', obligations=None, boundary='Stop', text='a statement', **meta):
    if obligations is None:
        obligations = [{'shape': 'LINEAGE', 'subject': 'source'}] if basis == 'source=source' else [{'shape': 'SPEC', 'subject': 'source', 'definition_id': 'd'}] if basis == 'def=d:source' else []
    meta['obligations'] = obligations
    if boundary == 'Stop':
        return event(boundary, stop_hook_active=True, last_assistant_message='makoto-basis: ' + basis + '\n' + text, makoto=meta)
    return event('PreToolUse', tool_name=boundary, tool_use_id='write',
                 tool_input={'file_path': 'new', 'content': text, 'description': 'makoto-basis: ' + basis}, makoto=meta)


class Session:
    def __init__(self, tmp_path, adapter='inferred', live=False):
        self.config = {'state_dir': str(tmp_path / 'state'), 'adapter': adapter}
        self.live = live
        self.events = []

    def send(self, ev):
        self.events.append(copy.deepcopy(ev))
        if self.live:
            return invoke(ev, self.config['state_dir'], self.config['adapter'])
        return hook.main(json.dumps(ev), self.config)

    def feed(self, events):
        for ev in events:
            assert not held(self.send(ev))

    def journal(self):
        return hook.sigma_read(hook.sigma_path(self.config['state_dir'], 'plant'), 'plant')


def plant(family, present, adapter):
    """Construction expected result chosen before live hook sees any event."""
    events = [event('UserPromptSubmit', prompt='turn')]
    basis = ''
    obligations = []
    if family == 'LINEAGE':
        basis = 'source=source'
        obligations = [{'shape': family, 'subject': 'source'}]
        if present:
            events += read_pair()
    elif family == 'SPEC':
        events[0]['makoto'] = {'definitions': [{'id': 'd', 'subject': 'source', 'revision': 'v', 'content': 'any definition'}]}
        basis = 'def=d:source'
        obligations = [{'shape': family, 'subject': 'source', 'definition_id': 'd', 'definition_revision': 'v'}]
        if present:
            events += read_pair(text='contradicts held definition')
    elif family == 'OTHER_POINT':
        events += read_pair(tid='first', place={'revision': 'before'})
        basis = 'second=source@after'
        obligations = [{'shape': family, 'subject': 'source', 'points': [{'revision': 'before'}, {'revision': 'after'}]}]
        if present:
            events += read_pair(tid='second', place={'revision': 'after'}, text='different value')
    elif family == 'SWITCH':
        basis = 'act=probe --input z->source'
        obligations = [{'shape': family, 'subject': 'source', 'input_sha256': 'input-z', 'selector': 'content'}]
        if present:
            pair = read_pair(tool='Bash', selector='content')
            pair[0]['makoto']['invocation'] = {'subject': 'source', 'selector': 'content', 'input_sha256': 'input-z'}
            events += pair
    # These obligations are host-owned; basis-like prose has no authority.
    events.append(output(basis, obligations))
    return events


@pytest.mark.parametrize('adapter', ['inferred'])
@pytest.mark.parametrize('family', ['SPEC', 'OTHER_POINT', 'SWITCH', 'LINEAGE'])
@pytest.mark.parametrize('present', [False, True])
def test_live_present_absent_plants(tmp_path, adapter, family, present):
    session = Session(tmp_path, adapter, live=True)
    events = plant(family, present, adapter)
    session.feed(events[:-1])
    response = session.send(events[-1])
    assert held(response) == (not present), response
    row = session.journal()[-1]
    assert bool(row['findings']) == (not present)
    if not present:
        assert family in {f['family'] for f in row['findings']}
    else:
        assert row['snapshot'] and all(s['reading_receipt_ids'] for s in row['snapshot'])


@pytest.mark.parametrize('adapter', ['inferred'])
@pytest.mark.parametrize('boundary', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'Stop', 'SubagentStop', 'commit', 'push'])
def test_every_boundary_and_retry_is_held(tmp_path, adapter, boundary):
    session = Session(tmp_path, adapter)
    ev = output('source=source', [{'shape': 'LINEAGE', 'subject': 'source'}], boundary='Write')
    if boundary in ('Stop', 'SubagentStop'):
        ev = output('source=source', [{'shape': 'LINEAGE', 'subject': 'source'}])
        ev['hook_event_name'] = boundary
    elif boundary in ('commit', 'push'):
        ev['tool_name'] = 'Bash'
        ev['tool_input'] = {'command': 'git -C /w ' + boundary, 'description': 'makoto-basis: source=source'}
    else:
        ev['tool_name'] = boundary
    assert held(session.send(ev))
    ev['stop_hook_active'] = True
    assert held(session.send(ev))
    assert session.journal()[-1]['stop_hook_active_unpaid']
    session.feed(read_pair())
    assert not held(session.send(ev))


@pytest.mark.parametrize('variant', ['pending', 'denied', 'replay', 'wrong_id', 'wrong_input', 'wrong_tool', 'failure', 'background', 'truncated', 'missing_content', 'partial', 'old_turn', 'similar_subject', 'relay', 'producer'])
def test_invalid_read_cannot_pay(tmp_path, variant):
    session = Session(tmp_path)
    pair = read_pair()
    if variant == 'pending':
        pair = pair[:1]
    elif variant == 'denied':
        pair[0]['makoto']['dependencies'] = [{'subject': 'missing'}]
        assert held(session.send(pair[0]))
        pair = pair[1:]
    elif variant == 'replay':
        session.feed(pair)
        session.send(event('UserPromptSubmit', prompt='next'))
    elif variant == 'wrong_id':
        pair[1]['tool_use_id'] = 'other'
    elif variant == 'wrong_input':
        pair[1]['tool_input'] = {'file_path': 'other'}
    elif variant == 'wrong_tool':
        pair[1]['tool_name'] = 'Bash'
    elif variant == 'failure':
        pair[1]['hook_event_name'] = 'PostToolUseFailure'
    elif variant == 'background':
        pair[1]['tool_response']['backgroundTaskId'] = 'task'
    elif variant == 'truncated':
        pair[1]['tool_response']['truncated'] = True
    elif variant == 'missing_content':
        pair[1]['tool_response'] = {}
    elif variant == 'partial':
        for ev in pair:
            ev['tool_input']['limit'] = 2
    elif variant == 'similar_subject':
        pair = read_pair('Source')
    elif variant in ('relay', 'producer'):
        pair[1]['makoto']['reads'] = [{'subject': 'source', 'complete': True, 'role': 'relay' if variant == 'relay' else 'source', 'producer': 'upstream' if variant == 'producer' else None}]
    session.feed(pair)
    if variant == 'old_turn':
        session.send(event('UserPromptSubmit', prompt='next'))
    assert held(session.send(output()))


@pytest.mark.parametrize('settlement', ['pending', 'success', 'partial_failure', 'no_effect'])
def test_mutation_epochs_and_reservations(tmp_path, settlement):
    session = Session(tmp_path)
    session.feed(read_pair())
    mutation = event('PreToolUse', tool_name='Write', tool_use_id='mutate', tool_input={'file_path': 'source', 'content': 'new', 'description': 'makoto-basis:'})
    assert not held(session.send(mutation))
    if settlement != 'pending':
        post = dict(mutation, hook_event_name='PostToolUse' if settlement == 'success' else 'PostToolUseFailure', tool_response={'content': 'ok'})
        if settlement == 'no_effect':
            post['makoto'] = {'no_effect': True}
        assert not held(session.send(post))
    assert held(session.send(output())) == (settlement != 'no_effect')
    if settlement == 'success':
        session.feed(read_pair(tid='reread'))
        assert held(session.send(output()))  # self-written bytes remain a relay


@pytest.mark.parametrize('origin', ['assistant', 'written', 'old_read', 'relay_read'])
def test_inferred_trace_values_are_awareness_only(tmp_path, origin):
    session = Session(tmp_path, 'inferred')
    if origin == 'assistant':
        assert not held(session.send(output('', text='731')))
    elif origin == 'written':
        write = output('', boundary='Write', text='731')
        assert not held(session.send(write))
        session.send(dict(write, hook_event_name='PostToolUse', tool_response={}))
    else:
        session.feed(read_pair(text='731', **({'role': 'relay'} if origin == 'relay_read' else {})))
        if origin == 'old_read':
            session.send(event('UserPromptSubmit', prompt='next'))
    assert not held(session.send(output('', text='731')))
    session.feed(read_pair(tid='original', text='731'))
    assert not held(session.send(output('', text='731')))


@pytest.mark.parametrize('tool,subject,selector', [('Read', 'a b/日本語', 'content'), ('Bash', 'source', 'content'), ('WebFetch', 'https://example.test/a?x=1#part', 'representation:body'), ('Grep', 'tree', 'query:{"path": "tree", "pattern": "z"}')])
def test_native_adapters_empty_content(tmp_path, tool, subject, selector):
    session = Session(tmp_path)
    pair = read_pair(subject, tool=tool, text='')
    if tool == 'Bash':
        for ev in pair:
            ev['tool_input'] = {'command': 'cat source'}
        pair[1]['tool_response']['exitCode'] = 0
    session.feed(pair)
    assert not held(session.send(output('', [{'shape': 'LINEAGE', 'subject': subject, 'selector': selector}])))


@pytest.mark.parametrize('change', ['digest', 'selector', 'version', 'subject', 'background'])
def test_switch_exact_invocation(tmp_path, change):
    session = Session(tmp_path, 'inferred')
    pair = read_pair(tool='Bash', selector='branch', version='v')
    pair[0]['makoto']['invocation'] = {'subject': 'source', 'selector': 'branch', 'input_sha256': 'z'}
    obligation = {'shape': 'SWITCH', 'subject': 'source', 'selector': 'branch', 'version': 'v', 'input_sha256': 'z'}
    if change == 'background':
        pair[1]['tool_response']['backgroundTaskId'] = 'b'
    else:
        obligation[{'digest': 'input_sha256'}.get(change, change)] = 'different'
    session.feed(pair)
    assert held(session.send(output('', [obligation])))


def test_multiple_shapes_and_subjects_are_audited(tmp_path):
    session = Session(tmp_path, 'inferred')
    obligations = [{'shape': 'LINEAGE', 'subject': 'a'}, {'shape': 'LINEAGE', 'subject': 'b'}, {'shape': 'SPEC', 'subject': 'a', 'definition_id': 'd'}, {'shape': 'OTHER_POINT', 'subject': 'a', 'points': [{'revision': 'x'}, {'revision': 'y'}]}, {'shape': 'SWITCH', 'subject': 'a', 'input_sha256': 'x'}]
    assert held(session.send(output('', obligations)))
    findings = session.journal()[-1]['findings']
    assert len(findings) == 5 and {f['family'] for f in findings} == {'SPEC', 'OTHER_POINT', 'SWITCH', 'LINEAGE'}


def test_transport_corruption_and_missing_identity_fail_closed(tmp_path):
    cfg = {'state_dir': str(tmp_path), 'adapter': 'inferred'}
    for raw in ('null', '[]', '{}', 'bad', '{"hook_event_name":"Stop","session_id":"","x":NaN}'):
        assert held(hook.main(raw, cfg))
    session = Session(tmp_path)
    session.feed(read_pair())
    path = hook.sigma_path(session.config['state_dir'], 'plant')
    path.write_text(path.read_text().replace('original', 'changed'))
    assert held(session.send(output()))


def test_definition_is_prior_immutable_and_subject_bound(tmp_path):
    session = Session(tmp_path)
    register = event('UserPromptSubmit', makoto={'definitions': [{'id': 'd', 'revision': 'v', 'subject': 'source', 'content': 'definition'}]})
    session.send(register)
    session.feed(read_pair('other'))
    assert held(session.send(output('def=d:source')))
    session.feed(read_pair(tid='actual-source'))
    assert not held(session.send(output('def=d:source')))
    register['makoto']['definitions'][0]['content'] = 'changed'
    assert held(session.send(register))


def test_other_point_replay_cannot_be_second_receipt(tmp_path):
    session = Session(tmp_path, 'inferred')
    pair = read_pair(place={'revision': 'x'})
    session.feed(pair)
    session.feed(pair)
    obligation = {'shape': 'OTHER_POINT', 'subject': 'source', 'points': [{'revision': 'x'}, {'revision': 'x'}]}
    assert held(session.send(output('', [obligation])))
    session.feed(read_pair(tid='second', place={'revision': 'x'}))
    assert not held(session.send(output('', [obligation])))


def test_inferred_relative_subject_and_mutated_destination(tmp_path):
    session = Session(tmp_path, 'inferred')
    session.feed(read_pair('dir/source.txt'))
    session.send(event('UserPromptSubmit', prompt='next'))
    assert not held(session.send(output('', text='dir/source.txt')))
    session.feed(read_pair('dir/source.txt', tid='fresh'))
    assert not held(session.send(output('', text='dir/source.txt')))
    mutation = event('PreToolUse', tool_name='Bash', tool_use_id='transfer', tool_input={'command': 'transfer'}, makoto={'effects': [{'subject': 'dir/source.txt'}], 'destination': {'authority': 'remote'}})
    assert not held(session.send(mutation))
    session.send(dict(mutation, hook_event_name='PostToolUse', tool_response={'exitCode': 0, 'stdout': ''}))
    assert held(session.send(output('', text='dir/source.txt')))
    session.feed(read_pair('dir/source.txt', tid='landed', place={'authority': 'remote'}, role='source'))
    assert not held(session.send(output('', text='dir/source.txt')))


def test_writes_and_unpaired_posts_cannot_forge_source_receipts(tmp_path):
    session = Session(tmp_path)
    write = output('', boundary='Write')
    session.send(write)
    post = dict(write, hook_event_name='PostToolUse', tool_response={'content': 'invented'}, makoto={'reads': [{'subject': 'source', 'complete': True}]})
    session.send(post)
    session.send(read_pair(tid='unpaired')[1])
    assert held(session.send(output()))
    assert session.journal()[-1]['unknown']


def test_session_separation(tmp_path):
    session = Session(tmp_path)
    session.feed(read_pair())
    assert held(session.send(dict(output(), session_id='child')))
    assert not held(session.send(output()))


def test_delivery_wrapper_prevents_final_bytes(tmp_path):
    env = dict(os.environ, MAKOTO_STATE_DIR=str(tmp_path / 'state'), MAKOTO_ADAPTER='inferred', PYTHONDONTWRITEBYTECODE='1')
    def deliver(ev):
        return subprocess.run([sys.executable, str(ROOT / 'tools/deliver.py')], input=json.dumps(ev), env=env, capture_output=True, text=True)
    denied = deliver(output(text='DELIVERY_MARKER'))
    assert denied.returncode == 2 and denied.stdout == ''
    for ev in read_pair():
        invoke(ev, tmp_path / 'state', 'inferred')
    admitted = deliver(output(text='DELIVERY_MARKER'))
    assert admitted.returncode == 0 and 'DELIVERY_MARKER' in admitted.stdout


def test_grading_driver_on_generated_events_only():
    # Call the driver with our own in-memory plant; never read a pairs file.
    for adapter in ('inferred',):
        for present in (False, True):
            events = plant('LINEAGE', present, adapter)
            session = {'id': 'generated', 'events': events, 'step_index': len(events) - 1, 'files': {'source': 'original'}}
            assert drive_session(session, adapter)['held'] == (not present)
    with pytest.raises(ValueError):
        drive_session({'events': [output()], 'step_index': 0, 'files': {'../escape': 'x'}}, 'inferred')


@pytest.mark.parametrize('command', ['# makoto-basis:\ngit commit -m change', 'echo ready && git push', 'git --git-dir=repo commit', 'git -c x=y push'])
def test_git_boundaries_are_structural(tmp_path, command):
    session = Session(tmp_path)
    session.feed(read_pair())
    ev = event('PreToolUse', tool_name='Bash', tool_use_id='git', tool_input={'command': command})
    assert not held(session.send(ev))
    assert 'LINEAGE: read this turn:' in session.journal()[-1]['surface']


def test_inferred_written_subject_is_recorded_even_without_read(tmp_path):
    session = Session(tmp_path, 'inferred')
    write = output('', boundary='Write', text='novel')
    assert not held(session.send(write))
    session.send(dict(write, hook_event_name='PostToolUse', tool_response={}))
    assert held(session.send(output('', text='/w/new')))


def test_worker_answer_is_relay_not_original(tmp_path):
    session = Session(tmp_path, 'inferred')
    pair = [event('PreToolUse', tool_name='Task', tool_use_id='worker', tool_input={'prompt': 'research'}), event('PostToolUse', tool_name='Task', tool_use_id='worker', tool_response={'content': '731'})]
    session.feed(pair)
    assert not held(session.send(output('', text='731')))
    session.feed(read_pair(text='731'))
    assert not held(session.send(output('', text='731')))


def test_host_turn_id_changes_apply_before_candidate_check(tmp_path):
    session = Session(tmp_path)
    pair = read_pair()
    for ev in pair:
        ev['makoto']['turn_id'] = 'first'
    session.feed(pair)
    assert held(session.send(output(turn_id='second')))
    pair = read_pair(tid='new-turn')
    for ev in pair:
        ev['makoto']['turn_id'] = 'second'
    session.feed(pair)
    assert not held(session.send(output(turn_id='second')))


def test_host_alias_binds_transfer_without_merging_equal_bytes(tmp_path):
    session = Session(tmp_path, 'inferred')
    session.feed(read_pair('origin', place={'authority': 'local'}))
    pair = read_pair('destination', tid='dest', place={'authority': 'remote'})
    pair[0]['makoto']['aliases'] = [{'alias': 'destination', 'subject': 'origin'}]
    session.feed(pair)
    obligation = {'shape': 'OTHER_POINT', 'subject': 'origin', 'points': [{'authority': 'local'}, {'authority': 'remote'}]}
    assert not held(session.send(output('', [obligation])))
    assert held(session.send(output('', [dict(obligation, subject='another')])))


def test_spec_definition_revision_is_exact(tmp_path):
    session = Session(tmp_path, 'inferred')
    session.send(event('Register', makoto={'definitions': [{'id': 'd', 'subject': 'source', 'revision': 'one'}]}))
    session.feed(read_pair())
    assert held(session.send(output('', [{'shape': 'SPEC', 'subject': 'source', 'definition_id': 'd', 'revision': 'two'}])))


def test_typed_identity_authorities_stay_separate(tmp_path):
    session = Session(tmp_path, 'inferred')
    subject = {'kind': 'object', 'authority': 'a', 'namespace': 'n', 'object': 'x', 'selector': 'content'}
    pair = read_pair(tool='Bash', selector='content')
    pair[1]['makoto']['reads'][0]['subject'] = subject
    session.feed(pair)
    assert not held(session.send(output('', [{'shape': 'LINEAGE', 'subject': subject}])))
    assert held(session.send(output('', [{'shape': 'LINEAGE', 'subject': dict(subject, authority='b')}])))


@pytest.mark.parametrize('fields', [{'makoto': []}, {'tool_input': []}, {'last_assistant_message': {}}, {'makoto': {'obligations': ['malformed']}}, {'makoto': {'place': 'malformed', 'reads': []}}])
def test_malformed_envelopes_fail_closed(tmp_path, fields):
    session = Session(tmp_path)
    ev = output('source=source')
    ev.update(fields)
    assert held(session.send(ev))


def test_mutation_without_tool_id_is_transport_failure(tmp_path):
    session = Session(tmp_path)
    ev = output('', boundary='Write')
    del ev['tool_use_id']
    assert held(session.send(ev))
