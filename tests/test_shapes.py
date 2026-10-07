"""Self-authored native plants for the three record holds, no external corpus."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import shlex

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'plugin'), str(ROOT / 'tools')]
from makoto2 import hook
from run_pairs import held, invoke, drive_session


def event(name, **fields):
    return dict(hook_event_name=name, session_id='plant', cwd='/w', **fields)


def pair(tool='Read', ti=None, text='source data', tid='read', **post):
    ti = ti or {'file_path': 'source.txt'}
    response = {'stdout': text, 'exitCode': 0} if tool == 'Bash' else {'content': text}
    return [event('PreToolUse', tool_name=tool, tool_use_id=tid, tool_input=ti),
            event('PostToolUse', tool_name=tool, tool_use_id=tid, tool_input=ti, tool_response=response, **post)]


def output(text='source data', boundary='Stop', tid='step'):
    if boundary in ('Stop', 'SubagentStop', 'PreDelivery'):
        # Rule plants use an active Stop after the informational note.
        return event(boundary, last_assistant_message=text, stop_hook_active=True)
    inputs = {'file_path': 'out.txt', 'content': text}
    if boundary == 'Edit':
        inputs = {'file_path': 'out.txt', 'old_string': 'source data', 'new_string': text}
    elif boundary == 'MultiEdit':
        inputs = {'file_path': 'out.txt', 'edits': [{'old_string': 'source data', 'new_string': text}]}
    elif boundary == 'NotebookEdit':
        inputs = {'notebook_path': 'out.txt', 'new_source': text}
    elif boundary in ('commit', 'push'):
        inputs = {'command': 'git ' + boundary + (' -m ' + shlex.quote(text) if boundary == 'commit' else '')}
        boundary = 'Bash'
    return event('PreToolUse', tool_name=boundary, tool_use_id=tid, tool_input=inputs)


class Session:
    def __init__(self, tmp_path, live=False):
        self.config = {'state_dir': str(tmp_path / 'state'), 'adapter': 'inferred'}
        self.live = live

    def send(self, ev):
        if self.live:
            return invoke(ev, self.config['state_dir'], 'inferred')
        return hook.main(json.dumps(ev), self.config)

    def feed(self, events):
        for ev in events:
            assert not held(self.send(ev))

    def journal(self):
        return hook.sigma_read(hook.sigma_path(self.config['state_dir'], 'plant'), 'plant')

    def rules(self):
        return {f['rule'] for f in self.journal()[-1]['findings']}


@pytest.mark.parametrize('boundary', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'commit', 'push', 'Stop', 'SubagentStop', 'PreDelivery'])
@pytest.mark.parametrize('present', [False, True])
def test_all_boundaries_and_retries(tmp_path, boundary, present):
    s = Session(tmp_path)
    # Destination and command syntax do not become authored claim literals.
    s.send(event('UserPromptSubmit', prompt='out.txt git commit push -m'))
    if present:
        s.feed(pair(text='literal_91'))
    # Seed identical native journal records in-process; all admission/retry
    # boundaries below still cross the real CLI transport.
    s.live = True
    ev = output('literal_91', boundary=boundary)
    expected_hold = not present and boundary != 'push'
    for index, retry in enumerate((False, True, True)):
        ev['tool_use_id'] = f'step-{index}'
        ev['stop_hook_active'] = retry
        response = s.send(ev)
        assert held(response) == expected_hold, response
        if expected_hold:
            assert 'rule a' in str(response)
            assert 'read an original artifact' in str(response)
            assert s.journal()[-1]['stop_hook_active_unpaid'] == retry
        elif boundary in ('Stop', 'SubagentStop', 'PreDelivery'):
            assert response == {}
        else:
            assert response['hookSpecificOutput']['additionalContext'] == hook.FOUR_QUESTIONS
        if present and boundary in ('Write', 'Edit', 'MultiEdit', 'NotebookEdit'):
            s.live = False
            s.send(dict(ev, hook_event_name='PostToolUse', tool_response={'content': 'ok'}))
            if boundary == 'NotebookEdit':
                s.feed(pair('NotebookExecute', {'notebook_path': 'out.txt'}, 'source data', tid=f'run-{index}'))
            else:
                s.feed(pair(ti={'file_path': 'out.txt'}, tid=f'readback-{index}'))
            s.live = True


@pytest.mark.parametrize('origin', ['none', 'assistant', 'written', 'worker'])
def test_a_original_reading_required(tmp_path, origin):
    s = Session(tmp_path)
    s.send(event('UserPromptSubmit', prompt='out.txt'))
    if origin == 'assistant':
        s.send(event('AssistantMessage', content='731'))
    elif origin == 'written':
        # Rejected writes do not mutate; host transcript may contain executed old writes.
        write = output('731', 'Write')
        s.feed(pair())
        assert held(s.send(write))
        s.send(dict(write, hook_event_name='PostToolUse', tool_response={'content': 'ok'}))
        mutation = output('source data', 'Write', tid='invalidate')
        mutation['tool_input']['file_path'] = 'source.txt'
        s.feed([mutation, dict(mutation, hook_event_name='PostToolUse', tool_response={'content': 'ok'})])
        s.feed(pair(ti={'file_path': 'out.txt'}, text='731', tid='own'))
        s.feed(pair(ti={'file_path': 'source.txt'}, tid='source-readback'))
    elif origin == 'worker':
        s.feed(pair('Task', {'prompt': 'source data'}, '731'))
    assert held(s.send(output('731')))
    assert 'a' in s.rules()
    s.feed(pair(ti={'file_path': 'original.txt'}, text='731', tid='original'))
    assert not held(s.send(output('731')))


@pytest.mark.parametrize('value', ['dir/file.txt', 'id_abc', 'camelCase', '1.2.3', 'x@y.test', 'ab-91'])
def test_b_absent_and_present_exact_form(tmp_path, value):
    s = Session(tmp_path)
    s.feed(pair())
    assert held(s.send(output(value)))
    assert 'a' in s.rules()
    s.feed(pair(text=value, tid='value'))
    if value == 'dir/file.txt':
        assert held(s.send(output(value))) and s.rules() == {'b'}
        s.feed(pair(ti={'file_path': value}, tid='thing'))
    assert not held(s.send(output(value)))


@pytest.mark.parametrize('observed,proposed', [('dir/file.txt', './dir/file.txt'), ('./dir/file.txt', 'dir/file.txt'), ('/w/source.txt', 'source.txt'), ('source.txt', '/w/source.txt'), ('id731', 'id73'), ('CamelCase', 'camelCase'), ('value_1', 'value_2')])
def test_b_near_miss_spelling_is_not_regenerated(tmp_path, observed, proposed):
    s = Session(tmp_path)
    s.feed(pair(ti={'file_path': 'carrier.txt'}, text=observed))
    assert held(s.send(output(proposed)))
    # DESIGN D15: a different spelling in carrier bytes is not literal origin.
    assert 'a' in s.rules()


def test_b_only_assistant_text_never_pays(tmp_path):
    s = Session(tmp_path)
    s.feed(pair())
    s.send(event('AssistantMessage', content='id_731'))
    for _ in range(3):
        assert held(s.send(output('id_731')))
        assert s.rules() == {'a', 'b'}
    s.feed(pair(text='id_731', tid='actual'))
    assert not held(s.send(output('id_731')))


def test_user_copied_span_is_given_but_still_needs_artifact(tmp_path):
    s = Session(tmp_path)
    s.send(event('UserPromptSubmit', prompt='Use `user_value_91`'))
    # CAUSES: user messages are source statements; own answers are not.
    assert not held(s.send(output('`user_value_91`')))
    assert s.rules() == set()
    s.feed(pair())
    assert not held(s.send(output('`user_value_91`')))


@pytest.mark.parametrize('tool', ['Read', 'Grep', 'Glob', 'Bash', 'CustomArtifact'])
def test_agnostic_tool_response_and_prior_input(tmp_path, tool):
    s = Session(tmp_path)
    ti = {'file_path': 'source.txt', 'query': 'query_91'}
    if tool == 'Bash':
        ti = {'command': 'cat source.txt', 'query': 'query_91'}
    s.feed(pair(tool, ti, 'observed_92'))
    assert held(s.send(output('query_91 observed_92')))
    assert s.rules() == {'a', 'b'}
    s.feed(pair(text='query_91', tid='returned'))
    assert not held(s.send(output('query_91 observed_92')))


@pytest.mark.parametrize('subject', ['https://example.test/a', 'widget@1.2.3', 'widget 1.2.3', 'widget==1.2.3'])
@pytest.mark.parametrize('tool', ['WebFetch', 'WebSearch', 'Bash'])
def test_c_external_subject_needs_current_online_call(tmp_path, subject, tool):
    s = Session(tmp_path)
    s.feed(pair(text=subject))  # Origin is paid; a named page still needs its own reading.
    assert held(s.send(output(subject))) == subject.startswith('https://')
    assert s.rules() == ({'b'} if subject.startswith('https://') else set())
    ti = {'url': subject, 'prompt': 'source data'} if tool == 'WebFetch' else {'query': subject} if tool == 'WebSearch' else {'command': 'curl https://example.test/a'}
    s.feed(pair(tool, ti, subject, tid='online'))
    if tool == 'WebSearch' and subject.startswith('https://'):
        assert not held(s.send(output(subject))) and s.rules() == set()
        s.feed(pair('WebFetch', {'url': subject}, subject, tid='page'))
    assert not held(s.send(output(subject)))
    s.send(event('UserPromptSubmit', prompt='next turn'))
    assert not held(s.send(output(subject)))
    assert s.rules() == set()


def test_c_bare_public_project_uses_host_classification(tmp_path):
    s = Session(tmp_path)
    s.send(event('UserPromptSubmit', prompt='project', makoto={'external_subjects': ['PublicWidget']}))
    s.feed(pair(text='PublicWidget'))
    assert not held(s.send(output('PublicWidget')))
    assert s.rules() == set()
    s.feed(pair('WebSearch', {'query': 'PublicWidget'}, 'PublicWidget', tid='online'))
    assert not held(s.send(output('PublicWidget')))


@pytest.mark.parametrize('variant', ['failed_fetch', 'local_git', 'echo_url', 'comment_url', 'wrong_url', 'pending_fetch'])
def test_c_network_near_misses(tmp_path, variant):
    s = Session(tmp_path)
    subject = 'https://example.test/a'
    s.feed(pair(text=subject))
    call = pair('Bash', {'command': 'curl ' + subject}, subject, tid='online')
    if variant == 'failed_fetch':
        call[1]['tool_response']['exitCode'] = 1
    elif variant == 'local_git':
        call[0]['tool_input']['command'] = 'git show HEAD'
    elif variant == 'echo_url':
        call[0]['tool_input']['command'] = 'echo ' + subject
    elif variant == 'comment_url':
        call[0]['tool_input']['command'] = 'cat source.txt # curl ' + subject
    elif variant == 'wrong_url':
        call = pair('WebFetch', {'url': 'https://example.test/other'}, 'other data', tid='online')
    elif variant == 'pending_fetch':
        call = call[:1]
    s.feed(call)
    assert held(s.send(output(subject)))
    assert s.rules() == {'b'}


def test_prompt_url_still_requires_online(tmp_path):
    s = Session(tmp_path)
    s.send(event('UserPromptSubmit', prompt='https://example.test/a'))
    s.feed(pair())
    assert held(s.send(output('https://example.test/a')))
    assert s.rules() == {'b'}


@pytest.mark.parametrize('tool', ['Write', 'Bash'])
@pytest.mark.parametrize('settlement', ['pending', 'success', 'failure', 'no_effect'])
def test_staleness_after_any_write_and_own_readback(tmp_path, tool, settlement):
    s = Session(tmp_path)
    s.send(event('UserPromptSubmit', prompt='source.txt'))
    s.feed(pair(text='data_91'))
    s.feed(pair(ti={'file_path': 'other.txt'}, text='other data', tid='other'))
    change = output('source data', 'Write', 'change') if tool == 'Write' else event('PreToolUse', tool_name='Bash', tool_use_id='change', tool_input={'command': 'touch source.txt'})
    if tool == 'Write':
        change['tool_input']['file_path'] = 'source.txt'
    assert not held(s.send(change))
    if settlement != 'pending':
        post = dict(change, hook_event_name='PostToolUseFailure' if settlement == 'failure' else 'PostToolUse', tool_response={'content': 'ok', 'exitCode': 0})
        if settlement == 'no_effect':
            post['makoto'] = {'no_effect': True}
        s.send(post)
    assert not held(s.send(output('data_91')))
    if settlement == 'success':
        s.feed(pair(text='data_91', tid='own'))
        assert not held(s.send(output('data_91')))
        s.feed(pair(ti={'file_path': 'independent.txt'}, text='data_91', tid='independent'))
        assert not held(s.send(output('data_91')))


@pytest.mark.parametrize('variant', ['unpaired', 'replay', 'wrong_input', 'wrong_tool', 'background', 'missing_content'])
def test_invalid_receipts_cannot_pay(tmp_path, variant):
    s = Session(tmp_path)
    call = pair(text='receipt_731')
    if variant == 'unpaired':
        call = call[1:]
    elif variant == 'replay':
        s.feed(call)
        s.feed([event('PreToolUse', tool_name='Bash', tool_use_id='mut', tool_input={'command': 'touch source.txt'}), event('PostToolUse', tool_name='Bash', tool_use_id='mut', tool_response={'stdout': '', 'exitCode': 0})])
    elif variant == 'wrong_input':
        call[1]['tool_input'] = {'file_path': 'other.txt'}
    elif variant == 'wrong_tool':
        call[1]['tool_name'] = 'Bash'
    elif variant == 'background':
        call[1]['tool_response']['backgroundTaskId'] = 'job'
    else:
        call[1]['tool_response'] = {}
    s.feed(call)
    assert held(s.send(output('receipt_731'))) == (variant != 'replay')


def test_old_read_is_eligible_until_subject_written(tmp_path):
    s = Session(tmp_path)
    s.feed(pair(text='data_91'))
    s.send(event('UserPromptSubmit', prompt='next turn'))
    assert not held(s.send(output('data_91')))
    s.feed(pair('Bash', {'command': 'touch source.txt'}, '', tid='mut'))
    assert not held(s.send(output('data_91')))
    # D17 needs a claimed point; the historical identifier reading still exists.
    assert s.rules() == set()


def test_session_separation_and_corruption(tmp_path):
    s = Session(tmp_path)
    s.feed(pair(text='data_91'))
    assert held(s.send(dict(output('data_91'), session_id='other')))
    assert not held(s.send(output('data_91')))
    path = hook.sigma_path(s.config['state_dir'], 'plant')
    path.write_text(path.read_text().replace('data_91', 'invented_91'))
    assert held(s.send(output('data_91')))


@pytest.mark.parametrize('raw', ['null', '[]', '{}', 'bad', '{"hook_event_name":"Stop","session_id":"x","x":NaN}'])
def test_malformed_transport_blocks(tmp_path, raw):
    assert held(hook.main(raw, {'state_dir': str(tmp_path), 'adapter': 'inferred'}))


def test_delivery_and_pairs_print_actual_admission(tmp_path):
    s = Session(tmp_path)
    ev = output('data_91')
    import os
    env = dict(os.environ, MAKOTO_STATE_DIR=s.config['state_dir'], PYTHONDONTWRITEBYTECODE='1')
    def deliver():
        return subprocess.run([sys.executable, str(ROOT / 'tools/deliver.py')], input=json.dumps(ev), env=env, capture_output=True, text=True)
    denied = deliver()
    assert denied.returncode == 2 and denied.stdout == ''
    s.feed(pair(text='data_91'))
    admitted = deliver()
    assert admitted.returncode == 0 and admitted.stdout == 'data_91'
    for present in (False, True):
        events = pair(text='data_91') if present else []
        events.append(ev)
        result = drive_session({'id': 'generated', 'events': events, 'step_index': len(events)-1}, 'inferred')
        assert result['held'] == (not present)
        assert 'response' in result


@pytest.mark.parametrize('command', ['# comment\ngit commit -m source', 'echo ready && git push', 'git --git-dir=repo commit', 'git -c x=y push', 'env X=1 git push', '/usr/bin/git push'])
def test_git_syntax_is_a_boundary(tmp_path, command):
    s = Session(tmp_path)
    ev = event('PreToolUse', tool_name='Bash', tool_use_id='git', tool_input={'command': command})
    from makoto2.observed import dependent
    assert dependent(ev)
    assert not held(s.send(ev))
    claim = output('unread_91', 'commit', tid='claim')
    assert held(s.send(claim))
    assert s.rules() == {'a', 'b'}


@pytest.mark.parametrize('text,named', [('Error: file not found', False), ('  at worker (file.py:19)', True), ('Traceback (most recent call last):', False)])
def test_raw_tool_output_checks_names_only(tmp_path, text, named):
    s = Session(tmp_path)
    s.feed(pair())
    assert held(s.send(output(text))) == named
    assert ('a' in s.rules()) == named
    s.feed(pair('Bash', {'command': 'probe'}, text, tid='log'))
    if named:
        s.feed(pair(ti={'file_path': 'file.py:19'}, text='source code', tid='thing'))
        s.feed(pair('Run', {'file_path': 'file.py:19'}, text='response', tid='run'))
    assert not held(s.send(output(text)))


def test_error_output_is_read_even_when_command_fails(tmp_path):
    s = Session(tmp_path)
    call = pair('Bash', {'command': 'probe'}, 'Error: file not found')
    call[1]['tool_response']['exitCode'] = 1
    s.feed(call)
    assert not held(s.send(output('Error: file not found')))


def test_candidate_content_and_tool_metadata_do_not_pay_themselves(tmp_path):
    s = Session(tmp_path)
    s.feed(pair())
    ev = output('invented_91')
    ev['makoto'] = {'reads': [{'subject': 'invented_91', 'complete': True}]}
    assert held(s.send(ev))
    assert s.rules() == {'a', 'b'}


def test_numeric_and_protocol_field_values_are_actual_tool_bytes(tmp_path):
    s = Session(tmp_path)
    call = pair()
    call[1]['tool_response'] = {'data_value': 731}
    s.feed(call)
    assert held(s.send(output('data_value 731 file_path')))
    assert {f['subject'] for f in s.journal()[-1]['findings']} == {'file_path'}
    assert not held(s.send(output('data_value 731')))


def test_pending_tool_input_counts_for_b_but_does_not_create_reading(tmp_path):
    s = Session(tmp_path)
    s.feed(pair())
    s.feed(pair(ti={'file_path': 'new_91.txt'}, tid='pending')[:1])
    assert held(s.send(output('new_91.txt')))
    assert s.rules() == {'a', 'b'}
    s.send(pair(ti={'file_path': 'new_91.txt'}, tid='pending')[1])
    assert not held(s.send(output('new_91.txt')))


def test_public_classification_on_candidate_is_host_only(tmp_path):
    s = Session(tmp_path)
    s.feed(pair(text='PublicWidget'))
    ev = output('PublicWidget')
    ev['makoto'] = {'external_subjects': ['PublicWidget']}
    assert not held(s.send(ev))
    assert s.rules() == set()


@pytest.mark.parametrize('command', ['python3 script.py', '/w/script.py', 'bash script.py'])
def test_run_response_from_own_executable_is_artifact_reading(tmp_path, command):
    s = Session(tmp_path)
    s.send(event('UserPromptSubmit', prompt='script.py'))
    s.feed(pair())
    write = output('source data', 'Write')
    write['tool_input']['file_path'] = 'script.py'
    assert not held(s.send(write))
    s.send(dict(write, hook_event_name='PostToolUse', tool_response={'content': 'ok'}))
    s.feed(pair('Bash', {'command': command}, 'observed_91', tid='execute'))
    assert not held(s.send(output('observed_91')))
    assert s.rules() == set()


def test_offline_package_command_does_not_pay_online(tmp_path):
    s = Session(tmp_path)
    s.feed(pair(text='widget@1.2.3'))
    s.feed(pair('Bash', {'command': 'npm install --offline widget@1.2.3'}, 'widget@1.2.3', tid='offline'))
    assert not held(s.send(output('widget@1.2.3')))
    assert s.rules() == set()


def test_malformed_pretool_uses_native_deny_transport(tmp_path):
    ev = output('data_91', 'Write')
    del ev['session_id']
    response = hook.main(json.dumps(ev), {'state_dir': str(tmp_path), 'adapter': 'inferred'})
    assert response['hookSpecificOutput']['permissionDecision'] == 'deny'
