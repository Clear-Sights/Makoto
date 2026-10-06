"""Own factual surface plants, each with a present and absent record."""
import json
import pytest
from test_shapes import Session, event, read_pair, output
from run_pairs import held, emitted_surface, drive_session


def step(text='a statement', boundary='Write'):
    return output('', boundary=boundary, text=text)


def mutate(session, subject='source', text='new', destination=None):
    pre = event('PreToolUse', tool_name='Write', tool_use_id='mutation',
                tool_input={'file_path': subject, 'content': text})
    if destination:
        pre['makoto'] = {'destination': destination}
    assert not held(session.send(pre))
    session.send(dict(pre, hook_event_name='PostToolUse', tool_response={'content': 'ok'}))


LABELS = [
    'LINEAGE: read this turn:',
    'LINEAGE: named or value-bearing subjects not read this turn:',
    'LINEAGE: values recorded only in assistant/relay/session-written text:',
    'OTHER POINT: read only once:',
    'OTHER POINT: last reading predates last recorded mutation:',
    'OTHER POINT: no reading at recorded point:',
    'SWITCH: commands this turn:',
    'SWITCH: session scripts/executables without a run after edit:',
    'SPEC: held definitions and bound reading:',
]


@pytest.mark.parametrize('line', range(len(LABELS)))
@pytest.mark.parametrize('present', [False, True])
def test_surface_line_present_absent(tmp_path, line, present):
    s = Session(tmp_path)
    candidate = step()
    if line == 0:
        s.feed(read_pair())
        if not present:
            s.send(event('UserPromptSubmit'))
    elif line == 1:
        candidate = step('/w/source')
        if not present:
            s.feed(read_pair())
    elif line == 2:
        s.send(output('', text='731'))
        candidate = step('731')
        if not present:
            s.feed(read_pair(text='731'))
    elif line == 3:
        s.feed(read_pair())
        if not present:
            s.feed(read_pair(tid='second'))
    elif line == 4:
        s.feed(read_pair())
        mutate(s)
        if not present:
            s.feed(read_pair(tid='after'))
    elif line == 5:
        mutate(s, destination={'authority': 'remote'})
        if not present:
            s.feed(read_pair(tid='after', place={'authority': 'remote'}))
    elif line == 6:
        pair = read_pair(tool='Bash')
        s.feed(pair)
        if not present:
            s.send(event('UserPromptSubmit'))
    elif line == 7:
        mutate(s, 'script.py', 'print(1)')
        if not present:
            pre = event('PreToolUse', tool_name='Bash', tool_use_id='run', tool_input={'command': 'python3 script.py'})
            s.send(pre)
            s.send(dict(pre, hook_event_name='PostToolUse', tool_response={'exitCode': 1, 'stdout': ''}))
    elif line == 8:
        if present:
            s.send(event('Register', makoto={'definitions': [{'id': 'd', 'subject': 'source', 'content': 'held'}]}))
    response = s.send(candidate)
    surface = emitted_surface(response)
    assert (LABELS[line] in surface) == present, surface
    assert surface == s.journal()[-1]['surface']
    assert len(surface.splitlines()) <= 15


@pytest.mark.parametrize('boundary', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'commit', 'push', 'Stop'])
def test_all_boundaries_emit_exact_surface(tmp_path, boundary):
    s = Session(tmp_path)
    s.feed(read_pair())
    candidate = step(boundary=boundary if boundary not in ('commit', 'push') else 'Write')
    if boundary in ('commit', 'push'):
        candidate['tool_name'] = 'Bash'
        candidate['tool_input'] = {'command': 'git ' + boundary}
    if boundary == 'Stop':
        candidate.pop('stop_hook_active')
    response = s.send(candidate)
    assert emitted_surface(response) == s.journal()[-1]['surface']
    assert LABELS[0] in emitted_surface(response)
    if boundary == 'Stop':
        assert held(response)
        candidate['stop_hook_active'] = True
        assert not held(s.send(candidate))
        assert emitted_surface(s.send(candidate)) == ''
    else:
        assert not held(response)


@pytest.mark.parametrize('present', [False, True])
@pytest.mark.parametrize('boundary', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'Stop'])
def test_stale_record_holds_and_readback_releases(tmp_path, present, boundary):
    s = Session(tmp_path)
    s.feed(read_pair())
    mutate(s)
    if present:
        s.feed(read_pair(tid='after'))
    candidate = step('/w/source', boundary)
    if boundary != 'Stop':
        candidate['tool_input']['file_path'] = 'source'
    assert held(s.send(candidate)) == (not present)


def test_surface_stop_once_does_not_release_exact_hold(tmp_path):
    s = Session(tmp_path)
    s.feed(read_pair())
    candidate = output('', [{'shape': 'LINEAGE', 'subject': 'missing'}])
    candidate.pop('stop_hook_active')
    first = s.send(candidate)
    assert held(first) and emitted_surface(first)
    candidate['stop_hook_active'] = True
    again = s.send(candidate)
    assert held(again) and emitted_surface(again) == ''


def test_caps_are_counted_and_deterministic(tmp_path):
    s = Session(tmp_path)
    for i in range(9):
        s.feed(read_pair('s' + str(i), tid='r' + str(i)))
    one = emitted_surface(s.send(step()))
    two = emitted_surface(s.send(step()))
    assert one == two and '+5 more' in one and len(one.splitlines()) <= 15


def test_command_inputs_and_nonzero_exit_exact(tmp_path):
    s = Session(tmp_path)
    s.feed(read_pair(tool='Bash'))
    line = next(l for l in emitted_surface(s.send(step())).splitlines() if l.startswith(LABELS[6]))
    record = json.loads(line[len(LABELS[6]):].strip())
    assert record['command'] == 'probe --input z'
    assert record['inputs'] == {'command': 'probe --input z'} and record['exit_status'] == 1


def test_definition_binds_one_prior_reading(tmp_path):
    s = Session(tmp_path)
    s.send(event('Register', makoto={'definitions': [{'id': 'd', 'subject': 'source'}]}))
    s.feed(read_pair(tid='first'))
    s.feed(read_pair(tid='last'))
    surface = emitted_surface(s.send(step()))
    assert '"reading":"last:0"' in surface
    assert '"reading":"first:0"' not in surface


def test_driver_reports_actual_emitted_text_only():
    events = read_pair() + [step(boundary='Stop')]
    events[-1].pop('stop_hook_active')
    result = drive_session({'id': 'own', 'events': events, 'step_index': 2}, 'inferred')
    assert result['held'] and result['surface'] == result['response']['reason']
    events[-1]['stop_hook_active'] = True
    result = drive_session({'id': 'own', 'events': events, 'step_index': 2}, 'inferred')
    assert not result['held'] and result['surface'] == ''


def test_declared_is_removed(tmp_path):
    s = Session(tmp_path, 'declared')
    assert 'adapter must be inferred' in str(s.send(step()))


@pytest.mark.parametrize('present', [False, True])
def test_stale_target_without_content_name(tmp_path, present):
    s = Session(tmp_path)
    mutate(s)
    if present:
        s.feed(read_pair(tid='after'))
    candidate = step('unrelated content')
    candidate['tool_input']['file_path'] = 'source'
    assert held(s.send(candidate)) == (not present)


def test_read_before_edit_does_not_pay_readback(tmp_path):
    s = Session(tmp_path)
    s.feed(read_pair())
    mutate(s)
    assert held(s.send(step('/w/source')))
    pair = read_pair(tid='partial')
    for ev in pair:
        ev['tool_input']['offset'] = 1
        ev['tool_input']['limit'] = 2
    s.feed(pair)
    assert held(s.send(step('/w/source')))


def test_script_edit_resets_run_record(tmp_path):
    s = Session(tmp_path)
    mutate(s, 'script.py', 'print(1)')
    pre = event('PreToolUse', tool_name='Bash', tool_use_id='run', tool_input={'command': 'python3 script.py'})
    s.send(pre)
    s.send(dict(pre, hook_event_name='PostToolUse', tool_response={'exitCode': 0, 'stdout': ''}))
    assert LABELS[7] not in emitted_surface(s.send(step()))
    s.feed(read_pair('script.py', tid='after'))
    edit = event('PreToolUse', tool_name='Edit', tool_use_id='edit', tool_input={'file_path': 'script.py', 'old_string': '1', 'new_string': '2'})
    assert not held(s.send(edit))
    s.send(dict(edit, hook_event_name='PostToolUse', tool_response={'content': 'ok'}))
    assert LABELS[7] in emitted_surface(s.send(step()))


def test_transfer_destination_fact_uses_reserved_destination(tmp_path):
    s = Session(tmp_path)
    mutate(s, destination={'authority': 'remote'})
    surface = emitted_surface(s.send(step()))
    assert '"point":{"authority":"remote"}' in surface


def test_relay_value_with_original_elsewhere_is_not_only_relay(tmp_path):
    s = Session(tmp_path)
    s.send(output('', text='731'))
    s.feed(read_pair('different', text='731'))
    assert LABELS[2] not in emitted_surface(s.send(step('731')))


@pytest.mark.parametrize('message', [None, ''])
def test_stop_without_message_still_surfaces_once(tmp_path, message):
    s = Session(tmp_path)
    s.feed(read_pair())
    candidate = event('Stop')
    if message is not None:
        candidate['last_assistant_message'] = message
    first = s.send(candidate)
    assert held(first) and LABELS[0] in emitted_surface(first)
    candidate['stop_hook_active'] = True
    retry = s.send(candidate)
    assert not held(retry) and emitted_surface(retry) == ''


@pytest.mark.parametrize('present', [False, True])
def test_unseen_relative_path_has_missing_reading_fact(tmp_path, present):
    s = Session(tmp_path)
    if present:
        s.feed(read_pair('dir/unread.txt'))
    response = s.send(step('dir/unread.txt'))
    assert not held(response)
    assert (LABELS[1] in emitted_surface(response)) == (not present)
    assert 'file:/w/dir/unread.txt' in emitted_surface(response)


@pytest.mark.parametrize('command,ran', [('python3 -V', False), ('./python3 -V', True)])
def test_path_resolution_does_not_invent_local_execution(tmp_path, command, ran):
    s = Session(tmp_path)
    mutate(s, 'python3', '#!/bin/sh\nexit 0')
    pre = event('PreToolUse', tool_name='Bash', tool_use_id='run', tool_input={'command': command})
    s.send(pre)
    s.send(dict(pre, hook_event_name='PostToolUse', tool_response={'exitCode': 0, 'stdout': ''}))
    assert (LABELS[7] in emitted_surface(s.send(step()))) == (not ran)


@pytest.mark.parametrize('tool', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'Bash'])
def test_only_writer_replacement_values_are_bound_to_target(tmp_path, tool):
    s = Session(tmp_path)
    if tool == 'Write':
        ti = {'file_path': 'source', 'content': '731'}
    elif tool == 'Edit':
        ti = {'file_path': 'source', 'old_string': '619', 'new_string': '731'}
    elif tool == 'MultiEdit':
        ti = {'file_path': 'source', 'edits': [{'old_string': '619', 'new_string': '731'}]}
    elif tool == 'NotebookEdit':
        ti = {'notebook_path': 'source', 'new_source': '731'}
    else:
        ti = {'command': 'transfer 619 731'}
    pre = event('PreToolUse', tool_name=tool, tool_use_id='mutation', tool_input=ti,
                makoto={'effects': [{'subject': 'unrelated'}]})
    assert not held(s.send(pre))
    s.send(dict(pre, hook_event_name='PostToolUse', tool_response={'exitCode': 0, 'stdout': ''}))
    surface = emitted_surface(s.send(step('619 731')))
    relay_lines = [line for line in surface.splitlines() if line.startswith(LABELS[2])]
    if tool == 'Bash':
        assert not relay_lines
    else:
        assert len(relay_lines) == 1
        assert '"subject":"file:/w/source"' in relay_lines[0]
        assert '"values":["731"]' in relay_lines[0]
        assert '619' not in relay_lines[0] and 'unrelated' not in relay_lines[0]


@pytest.mark.parametrize('present', [False, True])
def test_registered_subject_without_receipt_is_still_named(tmp_path, present):
    s = Session(tmp_path)
    s.send(event('Register', makoto={'definitions': [{'id': 'd', 'subject': 'source'}]}))
    if present:
        s.feed(read_pair())
    response = s.send(step('source'))
    assert not held(response)
    assert (LABELS[1] in emitted_surface(response)) == (not present)


@pytest.mark.parametrize('present', [False, True])
def test_exact_host_alias_name_uses_canonical_freshness(tmp_path, present):
    s = Session(tmp_path)
    mutate(s)
    s.send(event('Register', makoto={'aliases': [{'alias': 'destination', 'subject': 'source'}]}))
    if present:
        s.feed(read_pair('destination', tid='after'))
    response = s.send(step('destination'))
    assert held(response) == (not present)
    assert (LABELS[4] in emitted_surface(response)) is False
    assert (LABELS[5] in emitted_surface(response)) == (not present)


def test_native_shebang_does_not_classify_unrelated_host_effect(tmp_path):
    s = Session(tmp_path)
    pre = event('PreToolUse', tool_name='Write', tool_use_id='mutation',
                tool_input={'file_path': 'executable', 'content': '#!/bin/sh\nexit 0'},
                makoto={'effects': [{'subject': 'unrelated'}]})
    assert not held(s.send(pre))
    s.send(dict(pre, hook_event_name='PostToolUse', tool_response={'content': 'ok'}))
    surface = emitted_surface(s.send(step()))
    script_line = next(line for line in surface.splitlines() if line.startswith(LABELS[7]))
    assert 'file:/w/executable' in script_line and 'unrelated' not in script_line
