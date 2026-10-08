"""Ported live probes replay through the public CLI without external fixtures."""

import pytest

from test_shapes import event, pair, output
from run_pairs import invoke, held

BODY = 'echo hello\n'


def write(path, tid='write'):
    pre = event('PreToolUse', tool_name='Write', tool_use_id=tid,
                tool_input={'file_path': path, 'content': BODY})
    return [pre, dict(pre, hook_event_name='PostToolUse', tool_response={'content': 'ok'})]


def bash(command, tid='bash', text='ok'):
    return pair('Bash', {'command': command}, text, tid=tid)


def case(name, events, candidate, rules=()):
    return {'id': name, 'events': events + [candidate], 'step_index': len(events),
            'expected_rules': list(rules), 'expected_held': bool(rules)}


def cases():
    rows = []
    for command in ('mv old.log "$W/g$g/tiller.log.run1"', 'mv old.log "$W/g$g/tiller.log.run2"',
                    'mv old.log "$W/g$g/tiller.log.run3"', 'mv old.log tiller.log.run1',
                    'mv old.sh renamed.sh'):
        rows.append(case('rename-' + str(len(rows)), bash(command), output('Done')))
    for path in ('/home/user/l8/rerun.sh', '/mnt/project-files/PROGRESS/tiller/layer8-rerun.sh'):
        for launcher in ('sh codex-job.sh start rerun -- sh ', 'bash /home/user/codex-job.sh start rerun -- bash '):
            events = write(path) + bash(launcher + path, tid='launch', text='hello')
            rows.append(case('launcher-' + str(len(rows)), events, output('Done')))
    for path, content in (('new-script.sh', BODY), ('gate.txt', 'READY=yes\n')):
        candidate = event('PreToolUse', tool_name='Write', tool_use_id='create',
                          tool_input={'file_path': path, 'content': content})
        rows.append(case('creation-' + path, [], candidate))
    rows.append(case('missing-transcript-prompt', [], event('UserPromptSubmit', prompt='hi',
        transcript_path='/tmp/makoto-live-never-created/session.jsonl')))
    rows.append(case('missing-transcript-keeps-journal', [event('UserPromptSubmit', prompt='unread.txt')],
        dict(output('unread.txt'), transcript_path='/tmp/makoto-live-never-created/session.jsonl'), ('a', 'b',)))
    rows.append(case('git-identity', [], event('PreToolUse', tool_name='Bash', tool_use_id='commit',
        tool_input={'command': 'git -c user.name=Clear-Sights -c user.email=dev@clear-sights.test commit -m "Update"'})))
    for text in ('branch release/5.0.2', 'Makoto 5.0.2', 'remote origin', 'config user.email'):
        events = pair(ti={'file_path': 'source.txt'}, text=text)
        rows.append(case('local-' + str(len(rows)), events, output(text, 'commit')))
    for coordinate in ('branch=release/5.0.2', 'version=5.0.2', 'remote=origin', 'config=user.email'):
        text = 'local.txt ' + coordinate
        events = pair(ti={'file_path': 'local.txt'}, text=text)
        events[0]['makoto'] = {'place': {'branch': 'old'}}
        rows.append(case('local-point-' + coordinate, events, output(text, 'commit')))
    for command in ('git commit -m Update', 'git commit --only included.sh -m Update',
                    'git -C /w commit -m Update'):
        events = write('scratch.sh') + write('included.sh', tid='included')
        events += bash('sh included.sh', tid='run', text='hello') + bash('git add included.sh', tid='add')
        rows.append(case('outside-commit-' + str(len(rows)), events,
            event('PreToolUse', tool_name='Bash', tool_use_id='commit', tool_input={'command': command})))
    events = write('included.sh') + bash('git add included.sh', tid='add')
    rows.append(case('true-unrun-commit', events, output('Update', 'commit'), ('d',)))
    events = write('included.sh') + bash('sh included.sh', tid='run', text='hello')
    events += write('included.sh', tid='edit-again') + bash('git add included.sh', tid='add')
    rows.append(case('true-run-before-edit', events, output('Update', 'commit'), ('d',)))
    rows.append(case('true-named-unread', [event('UserPromptSubmit', prompt='unread.txt')], output('unread.txt'), ('a', 'b',)))
    events = write('included.sh') + bash('sh codex-job.sh start job -- sh -n included.sh', text='queued', tid='launch')
    events += bash('git add included.sh', tid='add')
    rows.append(case('true-launcher-noexec', events, output('Update', 'commit'), ('d',)))
    for ran in (False, True):
        events = write('old.sh')
        if ran:
            events += bash('sh old.sh', tid='run', text='hello')
        events += bash('mv old.sh renamed.sh', tid='rename') + bash('git add renamed.sh', tid='add')
        rows.append(case('rename-existing-' + str(ran), events, output('Update', 'commit'), () if ran else ('d',)))
    for command in ('git add included.sh && git commit -m Update',
                    'git add included.sh; git commit -m Update'):
        rows.append(case('true-combined-' + str(len(rows)), write('included.sh'),
            event('PreToolUse', tool_name='Bash', tool_use_id='commit', tool_input={'command': command}), ('d',)))
    for command, response in (('git status --porcelain', 'A  included.sh\n M scratch.sh\n'),
                              ('git diff --cached --name-only', 'included.sh\n')):
        events = write('included.sh') + write('scratch.sh', tid='scratch') + bash(command, tid='scope', text=response)
        events += bash('sh included.sh', tid='run', text='hello')
        rows.append(case('git-scope-output-' + str(len(rows)), events, output('Update', 'commit')))
    events = write('included.sh') + bash('git ls-files', tid='tracked', text='included.sh\n')
    rows.append(case('true-commit-am', events, event('PreToolUse', tool_name='Bash', tool_use_id='commit',
        tool_input={'command': 'git commit -am "Update"'}), ('d',)))
    events = write('scratch.sh') + bash('git add scratch.sh', tid='add') + bash('git reset -- scratch.sh', tid='reset')
    rows.append(case('reset-removes-commit-scope', events, output('Update', 'commit')))
    events = write('included.sh') + bash('sh included.sh', tid='run', text='hello')
    events += bash('git add included.sh', tid='add') + write('included.sh', tid='unstaged-edit')
    rows.append(case('staged-version-only', events, output('Update', 'commit')))
    for fresh in (False, True):
        target = 'https://amber.test/record.txt'
        events = pair('WebFetch', {'url': 'https://violet.test/record.txt'}, target)
        if fresh:
            events += pair('WebFetch', {'url': target}, target, tid='fresh')
        rows.append(case('external-url-' + str(fresh), events, output(target), () if fresh else ('c',)))
    return rows


CASES = cases()


@pytest.fixture(scope='module')
def live_replay(tmp_path_factory):
    directory = tmp_path_factory.mktemp('live-installed')
    replay = {}
    for case in CASES:
        state = directory / case['id']
        responses = [invoke(event, state, 'inferred') for event in case['events']]
        response = responses[case['step_index']]
        replay[case['id']] = {'response': response, 'held': held(response)}
    return replay


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_live_cli(case, live_replay):
    import re
    row = live_replay[case['id']]
    response = row['response']
    reason = response.get('reason', '') + response.get('hookSpecificOutput', {}).get('permissionDecisionReason', '')
    assert 'transport/contract failure' not in str(response), response
    assert set(re.findall(r'makoto rule ([abcd])', reason)) == set(case['expected_rules']), response
    assert row['held'] == case['expected_held'], response
