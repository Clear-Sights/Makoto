"""Invented pairs proving DESIGN D15–D18 at every dependent boundary."""
import copy
import json
import shlex

import pytest

from test_shapes import event, pair, output, Session
from makoto2.evaluate import evaluate
from makoto2.provenance import Ledger
from run_pairs import held

KINDS = ('Write', 'Edit', 'commit', 'Stop')
LITERAL_CASES = [
    ('returns v4.3', 'v4.3'), ('accepts v8.4', 'v8.4'),
    ('latency is 12 ms.', '12 ms'), ('count is 9.', '9'),
    ('stamp is 2026-10-06T19:24Z', '2026-10-06T19:24Z'),
]
DOUBLE_RULES = ('ab', 'ac', 'ad', 'bc', 'bd', 'cd')
CASES = [(rule, kind, variant) for rule in 'abcd' for kind in KINDS for variant in range(2)]
CASES += [('a', kind, 'literal-' + str(i)) for kind in KINDS for i in range(len(LITERAL_CASES))]
CASES += [(rule, kind, variant) for rule, variant in [('b', 'definition'), ('b', 'unrelated'), ('c', 'stale'), ('c', 'copy'), ('d', 'unchanged')] for kind in KINDS]

CASES += [(rules, kind, 'double') for rules in DOUBLE_RULES for kind in KINDS]


def candidate(text, kind):
    result = output(text, kind)
    if kind == 'commit':
        result['tool_input']['command'] = 'git commit -m ' + shlex.quote(text)
    return result



def build_extra(rule, kind, variant, clean):
    if variant.startswith('literal-'):
        # DESIGN D9/D15: the source contains the literal, never its prose label.
        text, value = LITERAL_CASES[int(variant.split('-')[1])]
        events = []
        repair = pair(text=value)
    elif variant in ('unrelated', 'copy'):
        # DESIGN D5/D16/D17: only an explicit copy relation joins different paths.
        text = '/w/right/cedar.txt'
        events = pair(ti={'file_path': 'catalog.txt'}, text=text)
        if variant == 'copy':
            events += [event('UserPromptSubmit', makoto={'aliases': [
                {'subject': text, 'alias': '/w/left/cedar.txt'}]})]
        events += pair(ti={'file_path': '/w/left/cedar.txt'}, text='plain content', tid='left')
        repair = pair(ti={'file_path': text}, text='plain content', tid='right')
    elif variant == 'definition':
        # DESIGN D16: a thing reading cannot stand in for its named definition.
        events = [event('UserPromptSubmit', makoto={'definitions': [
            {'subject': 'cedar.txt', 'definition': 'cedar-spec.txt'}]})]
        events += pair(ti={'file_path': 'cedar.txt'}, text='plain content')
        text = 'cedar.txt'
        repair = pair(ti={'file_path': 'cedar-spec.txt'}, text='definition', tid='definition')
    elif variant == 'unchanged':
        # DESIGN D18: behavior of existing code needs a run without an edit.
        events = pair(ti={'file_path': 'cedar.py'}, text='def leaf():\n    return 7\n')
        text = 'cedar.py returns a response'
        repair = pair('Run', {'file_path': 'cedar.py'}, 'returned', tid='run')
    elif variant == 'stale':
        # DESIGN D15/D17: a mutation changes freshness, never historical origin.
        events = pair(ti={'file_path': 'cedar.txt'}, text='result_317')
        change = event('PreToolUse', tool_name='Write', tool_use_id='change',
                       tool_input={'file_path': 'cedar.txt', 'content': 'updated'})
        events += [change, dict(change, hook_event_name='PostToolUse', tool_response={'content': 'ok'})]
        text = 'cedar.txt'
        repair = pair(ti={'file_path': 'cedar.txt'}, text='updated', tid='fresh')
    else:
        raise AssertionError(variant)
    return events + (repair if clean else []), candidate(text, kind)


def build_double(rules, kind, clean):
    # DESIGN D14, D19: each of ab, ac, ad, bc, bd, cd retains both
    # independent findings; repairing both needs clears exactly that set.
    events = pair(ti={'file_path': 'cedar.py'}, text='def leaf():\n    return 7\n')
    events[0]['makoto'] = {'place': {'host': 'staging'}}
    events += pair(ti={'file_path': 'catalog.txt'}, text='cedar.py host=production', tid='catalog')
    text = 'cedar.py host=production returns 317'
    if 'a' not in rules or clean:
        events += pair(ti={'file_path': 'measurement.txt'}, text='317', tid='origin')
    events += [event('UserPromptSubmit', makoto={'definitions': [
        {'subject': 'cedar.py', 'definition': 'cedar-spec.txt'}]})]
    if 'b' not in rules or clean:
        events += pair(ti={'file_path': 'cedar-spec.txt'}, text='definition', tid='definition')
    if 'c' not in rules or clean:
        reading = pair(ti={'file_path': 'cedar.py'}, text='def leaf():\n    return 7\n', tid='destination')
        reading[0]['makoto'] = {'place': {'host': 'production'}}
        events += reading
    if 'd' not in rules or clean:
        events += pair('Run', {'file_path': 'cedar.py'}, 'completed', tid='run')
    return events, candidate(text, kind)


def build(rule, kind, variant, clean):
    """Each clean twin supplies the missing evidence."""
    if variant == 'double':
        return build_double(rule, kind, clean)
    if isinstance(variant, str):
        return build_extra(rule, kind, variant, clean)
    subject = ('cedar.txt', 'juniper.txt')[variant]
    value = ('317', '619')[variant]
    events = []
    if rule == 'a':
        # DESIGN D15: the subject is read; only the asserted literal is absent.
        events += pair(ti={'file_path': subject}, text='plain content')
        text = subject + ' contains ' + value
        repair = pair(ti={'file_path': 'measurement.txt'}, text=value, tid='repair')
    elif rule == 'b':
        # DESIGN D16: exact source bytes naming a thing are not its own reading.
        events += pair(ti={'file_path': 'catalog.txt'}, text=subject)
        text = subject
        repair = pair(ti={'file_path': subject}, text='plain content', tid='repair')
    elif rule == 'c':
        # DESIGN D17: a source at another point does not establish this point.
        events += pair(ti={'file_path': subject}, text='plain content')
        events[0]['makoto'] = {'place': {'host': 'staging'}}
        # The destination path and coordinate are read as literals independently.
        events += pair(ti={'file_path': 'catalog.txt'}, text=subject + ' host=production', tid='catalog')
        text = subject + ' host=production'
        repair = pair(ti={'file_path': subject}, text='plain content', tid='repair')
        repair[0]['makoto'] = {'place': {'host': 'production'}}
    else:
        # DESIGN D18: full config/code readback is not an input/response run.
        subject = ('cedar.py', 'juniper.json')[variant]
        body = 'def leaf():\n    return 7\n' if variant == 0 else '{"leaf": 7}'
        write = event('PreToolUse', tool_name='Write', tool_use_id='change', tool_input={'file_path': subject, 'content': body})
        events += [write, dict(write, hook_event_name='PostToolUse', tool_response={'content': 'ok'})]
        events += pair(ti={'file_path': subject}, text=body)
        text = subject + ' returns a response'
        repair = pair('Run', {'file_path': subject}, 'completed', tid='repair')
    if clean:
        events += repair
    return events, candidate(text, kind)


def replay(events, proposed):
    ledger = Ledger()
    for ev in events:
        ledger.ingest(copy.deepcopy(ev))
    return evaluate(ledger, copy.deepcopy(proposed))[0]


@pytest.mark.parametrize('rule,kind,variant', CASES)
def test_built_pair(tmp_path, rule, kind, variant):
    for clean in (False, True):
        events, proposed = build(rule, kind, variant, clean)
        findings = replay(events, proposed)
        assert {f['rule'] for f in findings} == (set() if clean else set(rule)), findings
        # Cross the real hook with recorded historical events, then inspect the
        # persisted answer; do not execute the invented subjects.
        transcript = tmp_path / ('clean.jsonl' if clean else 'fault.jsonl')
        transcript.write_text(''.join(json.dumps(ev) + '\n' for ev in events))
        session = Session(tmp_path / str(clean))
        response = session.send(dict(proposed, transcript_path=str(transcript)))
        assert held(response) == (not clean), response
        assert session.journal()[-1]['findings'] == findings


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('text', ['', 'Thank you!', 'A new tale begins.'])
def test_asserts_nothing(tmp_path, kind, text):
    # DESIGN D8 and D14: no existing subject or asserted literal, no hold.
    session = Session(tmp_path)
    assert not held(session.send(candidate(text, kind)))
    assert session.rules() == set()


@pytest.mark.parametrize('kind', ('Write', 'Edit'))
def test_creation_and_claim_share_a_writer(tmp_path, kind):
    # DESIGN D7–D8: a new function is a creation; an external reference is a claim.
    plain = candidate('def new_leaf():\n    return 23\n', kind)
    assert replay([], plain) == []
    mixed = candidate('def new_leaf():\n    return "outside.txt"\n', kind)
    assert {f['rule'] for f in replay([], mixed)} == {'a', 'b'}
