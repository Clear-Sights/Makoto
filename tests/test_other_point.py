"""Invented subjects, paired locations and timestamps, no external corpus."""
import shlex

import pytest

from test_shapes import Session, event, output, pair
from run_pairs import held
from makoto2.evaluate import evaluate
from makoto2.provenance import Ledger


def feed(ledger, events):
    for row in events:
        ledger.ingest(row)


def candidate(text, boundary):
    row = output(text, boundary)
    row['stop_hook_active'] = False
    if boundary == 'commit':
        row['tool_input']['command'] = 'git commit -m ' + shlex.quote(text)
    return row


@pytest.mark.parametrize('boundary', ['Write', 'Edit', 'commit', 'Stop'])
@pytest.mark.parametrize('subject', [
    'aster.txt', 'beryl.txt', 'cirrus.txt',
    'damson.txt', 'egret.txt', 'fennel.txt',
])
@pytest.mark.parametrize('case', ['path', 'Write', 'Edit', 'host', 'branch', 'environment', 'copy', 'target'])
@pytest.mark.parametrize('fresh', [False, True], ids=['faulty', 'clean'])
def test_located_twins(boundary, subject, case, fresh):
    ledger = Ledger()
    target = '/w/right/' + subject
    point = {} if case in ('path', 'Write', 'Edit') else {case: 'amber'}
    claim = ' '.join(k + '=' + v for k, v in point.items()) + ' ' + target
    # Give exact spellings independently, so these tests isolate c.
    ledger.ingest(event('UserPromptSubmit', prompt=claim))
    feed(ledger, pair(text='source data', tid='original'))
    old = '/w/left/' + subject if case == 'path' else target
    if case == 'path':
        ledger.ingest(event('Register', makoto={'aliases': [{'subject': target, 'alias': old}]}))
    read = pair(ti={'file_path': old}, tid='old')
    read[0]['makoto'] = {'place': {case: 'violet'} if point else {}}
    feed(ledger, read)
    if case in ('Write', 'Edit'):
        change = output('source data', case, tid='change')
        change['tool_input']['file_path'] = target
        feed(ledger, [change, dict(change, hook_event_name='PostToolUse', tool_response={'content': 'ok'})])
    if fresh:
        read = pair(ti={'file_path': target}, tid='fresh')
        read[0]['makoto'] = {'place': point}
        feed(ledger, read)
    findings, _ = evaluate(ledger, candidate(claim, boundary))
    assert {f['rule'] for f in findings} == (set() if fresh else {'c'})


@pytest.mark.parametrize('boundary', ['Write', 'Edit', 'commit', 'Stop'])
def test_no_reading_is_not_other_point(boundary):
    ledger = Ledger()
    feed(ledger, pair())
    findings, _ = evaluate(ledger, candidate('/w/unseen/quartz.txt', boundary))
    assert {f['rule'] for f in findings} == {'a', 'b'}


@pytest.mark.parametrize('command,claim', [
    ('git show amber:fern.txt', 'branch=amber /w/fern.txt'),
    ('ssh amber cat /w/fern.txt', 'host=amber /w/fern.txt'),
])
def test_native_point_readings(command, claim):
    ledger = Ledger()
    ledger.ingest(event('UserPromptSubmit', prompt=claim))
    feed(ledger, pair('Bash', {'command': command}, 'source data'))
    assert evaluate(ledger, candidate(claim, 'Stop'))[0] == []
    assert {f['rule'] for f in evaluate(ledger, candidate(claim.replace('amber', 'violet'), 'Stop'))[0]} >= {'c'}


@pytest.mark.parametrize('variant', ['pending', 'failed', 'relay', 'assistant', 'wrong-copy', 'overlap'])
def test_invalid_or_overlapping_read_does_not_pay(variant):
    ledger = Ledger()
    target = '/w/fern.txt'
    ledger.ingest(event('UserPromptSubmit', prompt=target))
    feed(ledger, pair())
    feed(ledger, pair(ti={'file_path': target}, tid='old'))
    read = pair(ti={'file_path': target}, tid='new')
    if variant == 'overlap':
        feed(ledger, read[:1])
    change = output('source data', 'Write', tid='change')
    change['tool_input']['file_path'] = target
    feed(ledger, [change, dict(change, hook_event_name='PostToolUse', tool_response={'content': 'ok'})])
    if variant == 'pending':
        read = read[:1]
    elif variant == 'failed':
        read[1]['hook_event_name'] = 'PostToolUseFailure'
    elif variant == 'relay':
        read[0]['makoto'] = {'reads': [{'subject': target, 'role': 'relay'}]}
    elif variant == 'assistant':
        read = [event('AssistantMessage', content=target)]
    elif variant == 'wrong-copy':
        read = pair(ti={'file_path': '/elsewhere/fern.txt'}, tid='new')
    elif variant == 'overlap':
        read = read[1:]
    feed(ledger, read)
    assert 'c' in {f['rule'] for f in evaluate(ledger, candidate(target, 'Stop'))[0]}


def test_writer_destination_is_creation_not_a_claim():
    ledger = Ledger()
    feed(ledger, pair(ti={'file_path': '/elsewhere/out.txt'}))
    assert evaluate(ledger, candidate('source data', 'Write'))[0] == []


@pytest.mark.parametrize('boundary', ['Write', 'Edit', 'commit', 'Stop'])
@pytest.mark.parametrize('subject', ['iris.txt', 'juniper.txt', 'kelp.txt', 'larch.txt', 'mallow.txt', 'nettle.txt'])
@pytest.mark.parametrize('fresh', [False, True], ids=['faulty', 'clean'])
def test_native_admission_twins(tmp_path, boundary, subject, fresh):
    session = Session(tmp_path)
    target = '/w/right/' + subject
    session.send(event('UserPromptSubmit', prompt=target))
    session.send(event('Register', makoto={'aliases': [{'subject': target, 'alias': '/w/left/' + subject}]}))
    session.feed(pair(ti={'file_path': '/w/left/' + subject}))
    if fresh:
        session.feed(pair(ti={'file_path': target}, tid='right'))
    response = session.send(candidate(target, boundary))
    assert held(response) == (not fresh)
    assert session.rules() == (set() if fresh else {'c'})


@pytest.mark.parametrize('fresh', [False, True])
def test_url_host_is_a_point_even_after_online_search(fresh):
    ledger = Ledger()
    target = 'https://amber.test/fern.txt'
    feed(ledger, pair('WebFetch', {'url': 'https://violet.test/fern.txt'}, target))
    if fresh:
        feed(ledger, pair('WebFetch', {'url': target}, target, tid='right'))
    findings, _ = evaluate(ledger, candidate(target, 'Stop'))
    assert {f['rule'] for f in findings} == (set() if fresh else {'b', 'c'})


@pytest.mark.parametrize('spelling', ['/w/fern.txt', './fern.txt', 'fern.txt'])
def test_same_absolute_path_accepts_equivalent_spelling(spelling):
    ledger = Ledger()
    ledger.ingest(event('UserPromptSubmit', prompt=spelling))
    feed(ledger, pair(ti={'file_path': '/w/fern.txt'}))
    assert evaluate(ledger, candidate(spelling, 'Stop'))[0] == []


@pytest.mark.parametrize('command,paid', [
    ('true || cat /w/fern.txt', False),
    ('touch /w/fern.txt; cat /w/fern.txt', True),
    ('cat /w/fern.txt; touch /w/fern.txt', False),
])
def test_shell_selection_and_read_change_order(command, paid):
    ledger = Ledger()
    ledger.ingest(event('UserPromptSubmit', prompt='/w/fern.txt'))
    ledger.ingest(event('Register', makoto={'aliases': [{'subject': '/w/fern.txt', 'alias': '/other/fern.txt'}]}))
    feed(ledger, pair(ti={'file_path': '/other/fern.txt'}, tid='other'))
    feed(ledger, pair('Bash', {'command': command}, 'source data'))
    findings, _ = evaluate(ledger, candidate('/w/fern.txt', 'Stop'))
    assert ('c' not in {f['rule'] for f in findings}) == paid
