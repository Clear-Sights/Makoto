"""Independent plants for every switch clause and its form/ordering near misses."""
import json
import shlex
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
    candidate = output('Done' if boundary in ('commit', 'push') else 'branch.py returns a response', boundary)
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
    assert switch_holds(ledger, output(reference + ' returns a response', 'Write'))
    # D18: a value claim does not select a run.
    assert not switch_holds(ledger, output('branch.py recorded', 'Write'))


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


@pytest.mark.parametrize('variant', ['no_edits', 'source_read_only', 'no_effect', 'denied_without_mutation'])
def test_near_miss_no_executable_change(variant):
    ledger = Ledger()
    feed(ledger, pair(ti={'file_path': 'branch.py'}, text=CONTENT))
    if variant not in ('no_edits', 'source_read_only'):
        change = edit('branch.py')
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
    assert switch_holds(ledger, output('pkg.branch returns a response', 'Write'))
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


@pytest.mark.parametrize('command', ['head plan.toml', 'echo --config plan.toml', 'service --config other.toml plan.toml'])
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
    assert switch_holds(ledger, output('enabled returns a response', 'Write'))


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
    command = shlex.join([sys.executable.replace('\\', '/'), 'branch.py'])
    call = pair('Bash', {'command': command}, tid='run')
    for ev in call:
        ev['cwd'] = str(tmp_path)
    call[1]['hook_event_name'] = 'PostToolUseFailure'
    call[1]['tool_response'] = {'stdout': result.stdout, 'stderr': result.stderr, 'exitCode': result.returncode}
    s.feed(call)
    assert not held(s.send(dict(output('Done'), cwd=str(tmp_path))))


@pytest.mark.parametrize('rule,shape,subject', [('a', 'lineage', 'unread_91'), ('b', 'spec', './unread.txt'), ('c', 'other point', 'https://source.example.test/item')])
def test_other_hold_shapes_appear_in_transport_and_journal(tmp_path, rule, shape, subject):
    s = Session(tmp_path)
    if rule == 'b':
        s.send(event('UserPromptSubmit', prompt=subject))
    if rule == 'c':
        s.feed(pair(text=subject))
    if rule == 'c':
        s.feed(pair('WebFetch', {'url': 'https://other.example.test/item'}, subject, tid='other-point'))
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


@pytest.mark.parametrize('path,before,after,final', [
    ('./state/violet.json', '{"n":1}', '{"n":2}', './state/violet.json contains two.'),
    ('./settings/birch.toml', 'n = 1', 'n = 2', './settings/birch.toml contains two.'),
    ('./flags/cedar.ini', '[flags]\nn=1', '[flags]\nn=2', './flags/cedar.ini contains two.'),
])
def test_full_data_readback_pays_reported_shell_edit_shapes(tmp_path, path, before, after, final):
    s = Session(tmp_path)
    s.feed(pair(ti={'file_path': path}, text=before))
    s.feed(pair('Bash', {'command': "sed -i 's/1/2/' " + path}, '', tid='change'))
    assert held(s.send(output(final)))
    assert s.rules() == {'c', 'd'}
    s.feed(pair(ti={'file_path': path}, text=after, tid='readback'))
    assert held(s.send(output(final))) and s.rules() == {'d'}
    s.feed(pair('Run', {'file_path': path}, 'consumed', tid='run'))
    assert not held(s.send(output(final)))
    assert any(row.get('trace') == ['run'] and row.get('instruments') == 'makoto2.switch/execution-v1'
               for row in s.journal()[-1]['snapshot'])


@pytest.mark.parametrize('suffix', ['json', 'toml', 'ini', 'yaml', 'yml', 'cfg', 'conf', 'env'])
@pytest.mark.parametrize('reader', ['Read', 'cat'])
def test_data_forms_need_full_readback_after_edit(suffix, reader):
    ledger = Ledger()
    path = 'settings.' + suffix
    feed(ledger, edit(path))  # Declarations inside data do not select code mode.
    assert switch_holds(ledger)
    tool, ti = ('Read', {'file_path': path}) if reader == 'Read' else ('Bash', {'command': 'cat ' + path})
    feed(ledger, pair(tool, ti, 'new contents', tid='readback'))
    assert switch_holds(ledger)
    feed(ledger, pair('Run', {'file_path': path}, 'consumed', tid='run'))
    assert not switch_holds(ledger)


@pytest.mark.parametrize('variant', ['before_edit', 'later_edit', 'pending_edit', 'started_before_edit',
                                    'partial', 'search', 'wrong_path', 'missing', 'failed', 'truncated',
                                    'status_only', 'unpaired', 'relay'])
def test_data_readback_near_misses_still_hold(variant):
    ledger = Ledger()
    call = pair(ti={'file_path': 'settings.json'}, text='{"n":2}', tid='readback')
    if variant == 'before_edit':
        feed(ledger, call)
        feed(ledger, edit('settings.json'))
    elif variant == 'started_before_edit':
        feed(ledger, call[:1])
        feed(ledger, edit('settings.json'))
        feed(ledger, call[1:])
    else:
        feed(ledger, edit('settings.json'))
        if variant == 'partial':
            for ev in call:
                ev['tool_input']['limit'] = 1
        elif variant == 'search':
            call = pair('Bash', {'command': 'grep n settings.json'}, 'n', tid='readback')
        elif variant == 'wrong_path':
            call = pair(ti={'file_path': '/elsewhere/settings.json'}, tid='readback')
        elif variant == 'missing':
            call = call[:1]
        elif variant == 'failed':
            call[1]['hook_event_name'] = 'PostToolUseFailure'
        elif variant == 'truncated':
            call[1]['tool_response']['truncated'] = True
        elif variant == 'status_only':
            call[1]['tool_response'] = {'exitCode': 0}
        elif variant == 'unpaired':
            call = call[1:]
        elif variant == 'relay':
            call = pair('Task', {'request': 'read settings.json'}, 'contents', tid='readback',
                        makoto={'reads': [{'subject': 'settings.json', 'complete': True}]})
        feed(ledger, call)
        if variant in ('later_edit', 'pending_edit'):
            assert switch_holds(ledger)
            again = edit('settings.json', tid='again')
            feed(ledger, again[:1] if variant == 'pending_edit' else again)
    assert switch_holds(ledger)


@pytest.mark.parametrize('path', ['worker.py', 'worker.sh', 'worker.js', 'worker.ts', 'worker.json', 'worker.txt'])
@pytest.mark.parametrize('boundary', ['Stop', 'commit', 'push'])
def test_code_and_shebangs_still_require_runs_after_readback(path, boundary):
    ledger = Ledger()
    change = edit(path)
    if path.endswith(('.json', '.txt')):
        for ev in change:
            ev['tool_input']['content'] = '#!/bin/sh\necho hello\n'
    feed(ledger, change)
    feed(ledger, pair(ti={'file_path': path}, text=change[0]['tool_input']['content'], tid='readback'))
    assert switch_holds(ledger, output('Done', boundary))
    feed(ledger, pair('Run', {'file_path': path}, 'hello', tid='run'))
    assert not switch_holds(ledger, output('Done', boundary))


def test_shell_edit_of_observed_shebang_data_path_requires_run():
    ledger = Ledger()
    feed(ledger, pair(ti={'file_path': 'settings.json'}, text='#!/bin/sh\necho 1\n'))
    feed(ledger, pair('Bash', {'command': "sed -i 's/1/2/' settings.json"}, '', tid='change'))
    feed(ledger, pair(ti={'file_path': 'settings.json'}, text='#!/bin/sh\necho 2\n', tid='readback'))
    assert switch_holds(ledger)


def test_mixed_data_and_code_commit_requires_every_code_run():
    ledger = Ledger()
    feed(ledger, edit('settings.json'))
    feed(ledger, edit('first.py', tid='first'))
    feed(ledger, edit('second.py', tid='second'))
    feed(ledger, pair(ti={'file_path': 'settings.json'}, tid='data'))
    feed(ledger, pair(ti={'file_path': 'second.py'}, tid='code'))
    feed(ledger, pair('Run', {'file_path': 'first.py'}, 'response', tid='run_first'))
    assert [f['subject'] for f in switch_holds(ledger, output('Done', 'commit'))] == ['settings.json', 'second.py']
    feed(ledger, pair('Run', {'file_path': 'second.py'}, 'response', tid='run_second'))
    assert [f['subject'] for f in switch_holds(ledger, output('Done', 'commit'))] == ['settings.json']
    feed(ledger, pair('Run', {'file_path': 'settings.json'}, 'consumed', tid='config'))
    assert not switch_holds(ledger, output('Done', 'commit'))


@pytest.mark.parametrize('writer', ['Write', 'Edit'])
def test_full_data_replacement_removes_a_previous_shebang_obligation(writer):
    ledger = Ledger()
    change = edit('settings.txt')
    for ev in change:
        ev['tool_input']['content'] = '#!/bin/sh\necho 1\n'
    feed(ledger, change)
    feed(ledger, pair(ti={'file_path': 'settings.txt'}, text='#!/bin/sh\necho 1\n', tid='script'))
    assert switch_holds(ledger)
    feed(ledger, edit('settings.txt', tool=writer, tid='replace'))
    feed(ledger, pair(ti={'file_path': 'settings.txt'}, text=CONTENT, tid='data'))
    # D18: this replacement is still a program, even without its shebang.
    assert switch_holds(ledger)


def test_empty_full_data_read_is_a_witness():
    ledger = Ledger()
    feed(ledger, edit('settings.txt'))
    feed(ledger, pair(ti={'file_path': 'settings.txt'}, text='', tid='empty'))
    assert not switch_holds(ledger)


def test_wollemi_record_shape_passes_without_readback(tmp_path):
    s = Session(tmp_path)
    s.feed(pair(ti={'file_path': 'facts/mangrove.txt'}, text='The result is available.'))
    change = edit('out/wollemi.md', tid='record')
    for ev in change:
        ev['tool_input']['content'] = 'The result is saved.'
    s.feed(change)
    s.feed(pair(ti={'file_path': 'origins/araucaria.txt'}, text='pelican_seed', tid='origin'))
    assert held(s.send(output('out/wollemi.md records the result from pelican_seed.')))
    assert s.rules() == {'a', 'b'}
    s.feed(pair(ti={'file_path': 'out/wollemi.md'}, text='The result is saved.', tid='state'))
    assert not held(s.send(output('out/wollemi.md records the result from pelican_seed.')))
    assert not any(row.get('instruments', '').startswith('makoto2.switch/')
                   for row in s.journal()[-1]['snapshot'])


@pytest.mark.parametrize('path', ['record.md', 'record.txt', 'record.rst', 'record.csv', 'record.log', 'record'])
@pytest.mark.parametrize('boundary', ['Write', 'commit', 'push', 'Stop'])
@pytest.mark.parametrize('pending', [False, True])
def test_records_are_subtracted_even_with_code_like_contents(path, boundary, pending):
    ledger = Ledger()
    change = edit(path)
    feed(ledger, change[:1] if pending else change)
    # D18: syntactically declared code ships regardless of its suffix.
    assert bool(switch_holds(ledger, output(path, boundary))) == (boundary != 'Write')
    assert ledger.changed_code()


@pytest.mark.parametrize('path,expect_hold', [('record.txt', False), ('worker.py', True), ('worker', True)])
def test_commit_after_edit_preserves_script_obligations(tmp_path, path, expect_hold):
    s = Session(tmp_path)
    s.send(event('UserPromptSubmit', prompt='git commit -m #!/bin/sh'))
    s.feed(pair(text='The result is saved.'))
    if path == 'worker':
        s.feed(pair(ti={'file_path': '/bin/sh'}, text='interpreter', tid='interpreter'))
        s.feed(pair('Run', {'file_path': '/bin/sh'}, 'ready', tid='interpreter-run'))
    change = edit(path)
    for ev in change:
        ev['tool_input']['content'] = '#!/bin/sh\necho saved\n' if path == 'worker' else 'The result is saved.'
    s.feed(change)
    assert held(s.send(output('The result is saved.', 'commit'))) == expect_hold
    if expect_hold:
        assert s.rules() == {'d'}


def test_extensionless_executable_without_shebang_still_requires_run(tmp_path):
    path = tmp_path / 'worker'
    path.write_text('echo response\n')
    path.chmod(0o755)
    ledger = Ledger()
    feed(ledger, edit(str(path)))
    assert switch_holds(ledger, output('Done', 'commit'))
    feed(ledger, pair('Run', {'file_path': str(path)}, 'response', tid='run'))
    assert not switch_holds(ledger)


def test_observed_extensionless_shebang_survives_shell_edit():
    ledger = Ledger()
    feed(ledger, pair(ti={'file_path': 'worker'}, text='#!/bin/sh\necho 1\n'))
    feed(ledger, pair('Bash', {'command': "sed -i 's/1/2/' worker"}, '', tid='change'))
    assert switch_holds(ledger)


def test_plain_full_replacement_subtracts_former_record_script():
    ledger = Ledger()
    change = edit('record.txt')
    for ev in change:
        ev['tool_input']['content'] = '#!/bin/sh\necho 1\n'
    feed(ledger, change)
    assert switch_holds(ledger)
    replacement = edit('record.txt', tid='replace')
    for ev in replacement:
        ev['tool_input']['content'] = 'A plain record.'
    feed(ledger, replacement)
    assert not switch_holds(ledger)
