"""Independent plants for every switch clause and its form/ordering near misses."""
import json
import subprocess
import sys

import pytest

from test_shapes import Session, event, pair, output
from makoto2.evaluate import evaluate
from makoto2.provenance import Ledger
from makoto2.hook import FOUR_QUESTIONS
from run_pairs import held, drive_session


CONTENT = 'def dispatch(input_value):\n    return input_value + 1\n'


def feed(ledger, events):
    for ev in events:
        ledger.ingest(ev)


def edit(path='branch.py', tool='Write', tid='edit', **fields):
    ev = output(CONTENT, tool, tid=tid)
    key = 'notebook_path' if tool == 'NotebookEdit' else 'file_path'
    ev['tool_input'][key] = path
    ev.update(fields)
    return [ev, dict(ev, hook_event_name='PostToolUse', tool_response={'content': 'written'})]


def ledger_with_edit(path='branch.py', tool='Write'):
    ledger = Ledger()
    feed(ledger, pair(text=CONTENT + '\nbranch.py branch branchExtra.py pkg.branch input_value --config plan.toml'))
    ledger.ingest(event('UserPromptSubmit', prompt='git commit push -m out.txt branch.py'))
    feed(ledger, edit(path, tool))
    return ledger


def switch_holds(ledger, candidate=None):
    findings, _ = evaluate(ledger, candidate or output('Done'))
    return [finding for finding in findings if finding['rule'] == 'd']


@pytest.mark.parametrize('boundary', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'commit', 'push', 'Stop', 'SubagentStop', 'PreDelivery'])
def test_unrun_code_holds_each_dependent_boundary(boundary):
    ledger = ledger_with_edit()
    candidate = output('branch.py', boundary)
    if boundary in ('commit', 'push'):
        # Shipping needs no literal reference to the edited file.
        assert 'branch.py' not in candidate['tool_input']['command']
    holds = switch_holds(ledger, candidate)
    assert [(f['subject'], f['shape'], f['missing']) for f in holds] == [
        ('branch.py', 'switch', 'UNRUN CHANGE: run it and read the output before this step')]
    feed(ledger, pair('Bash', {'command': 'python3 branch.py'}, 'observed response', tid='run'))
    assert not switch_holds(ledger, candidate)


@pytest.mark.parametrize('reference', ['branch.py', './branch.py', '/w/branch.py', '`branch.py`', 'branch.py:19', 'branch.py:19:4', 'branch', 'dispatch', 'input_value'])
def test_writer_references_path_module_or_declared_identifier(reference):
    ledger = ledger_with_edit()
    assert switch_holds(ledger, output(reference, 'Write'))
    # Behaving words are not consulted: merely naming a changed subject holds.
    assert switch_holds(ledger, output('branch.py recorded', 'Write'))


@pytest.mark.parametrize('text', ['Works correctly and is done', 'branchExtra.py', 'dispatchExtra', 'unrelated text'])
def test_unrelated_writer_does_not_hold_by_meaning_or_substring(text):
    ledger = ledger_with_edit()
    assert not switch_holds(ledger, output(text, 'Write'))
    # Every final after edits is shipping, regardless of its words.
    assert switch_holds(ledger, output(text))


@pytest.mark.parametrize('tool', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit'])
@pytest.mark.parametrize('path', ['branch.py', 'branch.sh', 'plan.toml', 'plan.json', 'branch.ipynb'])
def test_each_native_writer_tracks_code_script_and_config(tool, path):
    ledger = ledger_with_edit(path, tool)
    assert switch_holds(ledger)
    runner = 'NotebookExecute' if tool == 'NotebookEdit' else 'Run'
    feed(ledger, pair(runner, {'file_path': path}, 'response', tid='run'))
    assert not switch_holds(ledger)


@pytest.mark.parametrize('path,content', [
    ('branch', '#!/bin/sh\necho response\n'),
    ('branch', 'def dispatch():\n    return 1\n'),
    ('Dockerfile', 'FROM scratch\n'),
    ('.env', 'PORT=731\n'),
    ('branch.custom', 'def dispatch():\n    return 1\n'),
    ('plan.data', '{"enabled": true}'),
])
def test_extensionless_code_and_config_forms(path, content):
    ledger = Ledger()
    change = edit(path)
    change[0]['tool_input']['content'] = content
    change[1]['tool_input']['content'] = content
    feed(ledger, change)
    assert switch_holds(ledger)
    feed(ledger, pair('Run', {'file_path': path}, 'response', tid='run'))
    assert not switch_holds(ledger)


@pytest.mark.parametrize('variant', ['no_edits', 'source_read_only', 'prose', 'no_effect', 'denied_without_mutation'])
def test_near_miss_no_executable_change(variant):
    ledger = Ledger()
    feed(ledger, pair(ti={'file_path': 'branch.py'}, text=CONTENT))
    if variant not in ('no_edits', 'source_read_only'):
        change = edit('report.md' if variant == 'prose' else 'branch.py')
        if variant == 'no_effect':
            change[1]['makoto'] = {'no_effect': True}
            change[1]['hook_event_name'] = 'PostToolUseFailure'
        if variant == 'denied_without_mutation':
            ledger.ingest(change[0], admitted=False)
        else:
            feed(ledger, change)
    assert not switch_holds(ledger)


@pytest.mark.parametrize('command', [
    'python branch.py', 'python3 -u ./branch.py', '/w/branch.py',
    'env MODE=731 python3 branch.py', 'python3 -m branch',
    'command python3 branch.py', 'exec python3 branch.py',
    'python3 branch.py --help', 'python3 branch.py -c', 'python3 -mbranch',
    'python3 -m branch --version', 'python3 -- branch.py',
    'python3 -m pytest branch.py',
])
def test_exact_invocation_with_output_pays(command):
    ledger = ledger_with_edit()
    feed(ledger, pair('Bash', {'command': command}, 'response', tid='run'))
    assert not switch_holds(ledger)
    _, snapshot = evaluate(ledger, output('Done'))
    assert any(item.get('trace') == ['run'] and item.get('instruments') == 'makoto2.switch/execution-v1' for item in snapshot)


@pytest.mark.parametrize('tool,ti', [
    ('Read', {'file_path': 'branch.py'}),
    ('Bash', {'command': 'cat branch.py'}),
    ('Bash', {'command': 'echo branch.py'}),
    ('Bash', {'command': 'python3 branchExtra.py branch.py'}),
    ('Bash', {'command': 'python3 -c "print(731)" branch.py'}),
    ('Bash', {'command': 'python3 -cprint(731) branch.py'}),
    ('Bash', {'command': 'python3 --version branch.py'}),
    ('Bash', {'command': 'node --check branch.py'}),
    ('Bash', {'command': 'bash -n branch.py'}),
    ('Bash', {'command': 'bash -s branch.py'}),
    ('Bash', {'command': 'python3 -W branch.py other.py'}),
    ('Bash', {'command': 'python3 -m other.branch'}),
    ('Bash', {'command': 'false && python3 branch.py'}),
    ('Bash', {'command': 'true || python3 branch.py'}),
    ('Bash', {'command': 'echo "python3 branch.py"'}),
    ('Task', {'file_path': 'branch.py'}),
    ('Query', {'file_path': 'branch.py'}),
    ('Run', {'file_path': 'branchExtra.py'}),
])
def test_readbacks_mentions_unselected_branches_and_different_paths_do_not_pay(tool, ti):
    ledger = ledger_with_edit()
    feed(ledger, pair(tool, ti, CONTENT, tid='wrong'))
    assert switch_holds(ledger)


@pytest.mark.parametrize('timing', ['before_edit', 'started_before_edit', 'second_edit', 'pending_edit', 'earlier_turn_run'])
def test_run_must_start_after_last_edit(timing):
    ledger = Ledger()
    call = pair('Bash', {'command': 'python3 branch.py'}, 'response', tid='run')
    if timing in ('before_edit', 'earlier_turn_run'):
        feed(ledger, call)
        if timing == 'earlier_turn_run':
            ledger.ingest(event('UserPromptSubmit', prompt='edit now'))
        feed(ledger, edit())
    elif timing == 'started_before_edit':
        feed(ledger, call[:1])
        feed(ledger, edit())
        feed(ledger, call[1:])
    else:
        feed(ledger, edit())
        feed(ledger, call)
        assert not switch_holds(ledger)
        feed(ledger, edit(tid='again')[:1] if timing == 'pending_edit' else edit(tid='again'))
    assert switch_holds(ledger)
    if timing == 'pending_edit':
        pending = edit(tid='again')[1]
        ledger.ingest(pending)
    feed(ledger, pair('Bash', {'command': 'python3 branch.py'}, 'new response', tid='fresh'))
    assert not switch_holds(ledger)


def test_previous_turn_run_remains_paid_without_new_edit():
    ledger = ledger_with_edit()
    feed(ledger, pair('Bash', {'command': 'python3 branch.py'}, 'response', tid='run'))
    ledger.ingest(event('UserPromptSubmit', prompt='report again'))
    assert not switch_holds(ledger)


def test_replayed_run_receipt_cannot_pay_a_later_edit():
    ledger = ledger_with_edit()
    call = pair('Bash', {'command': 'python3 branch.py'}, 'response', tid='run')
    feed(ledger, call)
    assert not switch_holds(ledger)
    feed(ledger, edit(tid='again'))
    feed(ledger, call)
    assert switch_holds(ledger)


def test_package_module_name_and_run_resolve_the_same_recorded_path():
    ledger = ledger_with_edit('pkg/branch.py')
    assert switch_holds(ledger, output('pkg.branch', 'Write'))
    feed(ledger, pair('Bash', {'command': 'python3 -m pkg.branch'}, 'response', tid='run'))
    assert not switch_holds(ledger)


@pytest.mark.parametrize('variant', ['pending', 'missing', 'unpaired', 'wrong_tool', 'wrong_input', 'background', 'empty_receipt', 'assistant_claim', 'candidate_receipt'])
def test_missing_or_invalid_execution_output_does_not_pay(variant):
    ledger = ledger_with_edit()
    call = pair('Bash', {'command': 'python3 branch.py'}, 'response', tid='run')
    if variant == 'pending':
        call = call[:1]
    elif variant == 'missing':
        call[1].pop('tool_response')
    elif variant == 'unpaired':
        call = call[1:]
    elif variant == 'wrong_tool':
        call[1]['tool_name'] = 'Read'
    elif variant == 'wrong_input':
        call[1]['tool_input'] = {'command': 'python3 branchExtra.py'}
    elif variant == 'background':
        call[1]['tool_response'] = {'backgroundTaskId': 'job', 'stdout': '', 'exitCode': 0}
    elif variant == 'empty_receipt':
        call[1]['tool_response'] = {}
    elif variant in ('assistant_claim', 'candidate_receipt'):
        call = [event('AssistantMessage', content='Ran branch.py and read response')]
    feed(ledger, call)
    candidate = output('Done')
    if variant == 'candidate_receipt':
        candidate['makoto'] = {'invocation': {'subject': 'branch.py'}}
    assert switch_holds(ledger, candidate)


@pytest.mark.parametrize('response', [
    {'stdout': 'Traceback: failure', 'exitCode': 1},
    {'stderr': 'failure', 'exit_code': 1},
    {'stdout': '', 'exitCode': 0},
    {'backgroundTaskId': 'job', 'stdout': 'actual process output'},
])
def test_failed_silent_or_background_run_with_actual_output_pays(response):
    ledger = ledger_with_edit()
    call = pair('Bash', {'command': 'python3 branch.py'}, tid='run')
    call[1]['tool_response'] = response
    if response.get('exitCode') == 1 or response.get('exit_code') == 1:
        call[1]['hook_event_name'] = 'PostToolUseFailure'
    feed(ledger, call)
    assert not switch_holds(ledger)


def test_one_run_cannot_pay_another_edited_path_with_same_basename():
    ledger = ledger_with_edit('left/branch.py')
    feed(ledger, edit('right/branch.py', tid='right'))
    feed(ledger, pair('Bash', {'command': 'python3 left/branch.py'}, 'response', tid='run'))
    assert [f['subject'] for f in switch_holds(ledger)] == ['right/branch.py']


def test_cwd_is_part_of_execution_identity():
    ledger = ledger_with_edit()
    call = pair('Bash', {'command': 'python3 branch.py'}, 'response', tid='wrong')
    feed(ledger, [dict(ev, cwd='/other') for ev in call])
    assert switch_holds(ledger)
    feed(ledger, pair('Bash', {'command': 'python3 /w/branch.py'}, 'response', tid='right'))
    assert not switch_holds(ledger)


@pytest.mark.parametrize('command', ['service --config plan.toml', 'service --config=plan.toml'])
def test_run_consumes_exact_config_option(command):
    ledger = ledger_with_edit('plan.toml')
    feed(ledger, pair('Bash', {'command': command}, 'response', tid='run'))
    assert not switch_holds(ledger)


@pytest.mark.parametrize('command', ['cat plan.toml', 'echo --config plan.toml', 'service --config other.toml plan.toml'])
def test_config_mentions_and_different_config_do_not_pay(command):
    ledger = ledger_with_edit('plan.toml')
    feed(ledger, pair('Bash', {'command': command}, 'response', tid='run'))
    assert switch_holds(ledger)


@pytest.mark.parametrize('tool,ti', [('Bash', {'command': 'touch branch.py'}), ('CustomMutation', {})])
def test_shell_and_opaque_recorded_mutations_invalidate_run(tool, ti):
    ledger = ledger_with_edit()
    feed(ledger, pair('Bash', {'command': 'python3 branch.py'}, 'response', tid='run'))
    call = pair(tool, ti or {'operation': 'change'}, 'updated', tid='change')
    if tool == 'CustomMutation':
        call[0]['makoto'] = {'effects': [{'subject': 'branch.py'}]}
    feed(ledger, call)
    assert switch_holds(ledger)


@pytest.mark.parametrize('denied', [False, True])
def test_failed_or_reported_denied_edit_requires_run(denied):
    ledger = Ledger()
    change = edit()
    ledger.ingest(change[0], admitted=not denied)
    change[1]['hook_event_name'] = 'PostToolUseFailure'
    ledger.ingest(change[1])
    assert switch_holds(ledger)
    feed(ledger, pair('Bash', {'command': 'python3 branch.py'}, 'response', tid='run'))
    assert not switch_holds(ledger)


@pytest.mark.parametrize('command', ['. branch.sh', 'source branch.sh'])
def test_sourcing_a_script_executes_it(command):
    ledger = ledger_with_edit('branch.sh')
    feed(ledger, pair('Bash', {'command': command}, 'response', tid='run'))
    assert not switch_holds(ledger)


def test_compact_json_key_is_a_named_edited_identifier():
    ledger = Ledger()
    change = edit('plan.json')
    for ev in change:
        ev['tool_input']['content'] = '{"enabled": true}'
    feed(ledger, change)
    assert switch_holds(ledger, output('enabled', 'Write'))


def test_recorded_command_write_requires_execution_of_that_script():
    ledger = Ledger()
    feed(ledger, pair('Bash', {'command': 'printf response > branch.sh'}, '', tid='write'))
    assert switch_holds(ledger)
    feed(ledger, pair('Bash', {'command': 'bash branch.sh'}, 'response', tid='run'))
    assert not switch_holds(ledger)


@pytest.mark.parametrize('spoof', [False, True])
@pytest.mark.parametrize('where', ['pre', 'post'])
def test_opaque_actual_invocation_witness_is_host_owned(spoof, where):
    ledger = ledger_with_edit()
    call = pair('CustomRunner', {'request': 'execute'}, 'response', tid='run')
    ev = call[where == 'post']
    target = ev['tool_input'] if spoof else ev
    target['makoto'] = {'invocation': {'subjects': ['branch.py']}}
    feed(ledger, call)
    assert bool(switch_holds(ledger)) == spoof


def test_live_holds_and_unpaid_stop_retries_have_switch_tag(tmp_path):
    s = Session(tmp_path, live=True)
    s.feed(pair(text=CONTENT))
    change = edit()
    s.feed(change)
    for active in (False, True, True):
        response = s.send(dict(output('Done'), stop_hook_active=active))
        assert held(response)
        assert 'rule d [switch]' in response['reason']
        assert 'branch.py' in response['reason']
        assert 'run it and read the output before this step' in response['reason']
        assert FOUR_QUESTIONS not in response['reason']
        assert s.rules() == {'d'}
    s.feed(pair('Bash', {'command': 'python3 branch.py'}, 'response', tid='run'))
    assert s.send(output('Done')) == {}


def test_live_failed_real_run_response_pays(tmp_path):
    s = Session(tmp_path)
    code = 'raise RuntimeError("response")\n'
    s.feed(pair(text=code))
    change = edit()
    for ev in change:
        ev['cwd'] = str(tmp_path)
        ev['tool_input']['content'] = code
    s.feed(change)
    (tmp_path / 'branch.py').write_text(code)
    result = subprocess.run([sys.executable, 'branch.py'], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 1 and 'RuntimeError: response' in result.stderr
    call = pair('Bash', {'command': f'{sys.executable} branch.py'}, tid='run')
    for ev in call:
        ev['cwd'] = str(tmp_path)
    call[1]['hook_event_name'] = 'PostToolUseFailure'
    call[1]['tool_response'] = {'stdout': result.stdout, 'stderr': result.stderr, 'exitCode': result.returncode}
    s.feed(call)
    assert not held(s.send(dict(output('Done'), cwd=str(tmp_path))))


@pytest.mark.parametrize('rule,shape,subject', [('a', 'lineage', 'source'), ('b', 'spec', 'unread_identifier'), ('c', 'other point', 'https://source.example.test/item')])
def test_other_hold_shapes_appear_in_transport_and_journal(tmp_path, rule, shape, subject):
    s = Session(tmp_path)
    if rule != 'a':
        s.feed(pair(text=subject if rule == 'c' else 'source'))
    response = s.send(output(subject))
    assert f'rule {rule} [{shape}]' in response['reason']
    assert next(f for f in s.journal()[-1]['findings'] if f['rule'] == rule)['shape'] == shape


def test_imported_edits_and_pair_runner_keep_exact_switch_response(tmp_path):
    events = pair(text=CONTENT) + edit() + [output('Done')]
    result = drive_session({'id': 'switch-plant', 'events': events, 'step_index': len(events) - 1}, 'inferred')
    assert result['held'] and 'rule d [switch]' in result['response']['reason']
    transcript = tmp_path / 'history.jsonl'
    transcript.write_text(''.join(json.dumps(ev) + '\n' for ev in events[:-1]))
    s = Session(tmp_path)
    assert held(s.send(dict(output('Done'), transcript_path=str(transcript))))
    assert s.rules() == {'d'}
