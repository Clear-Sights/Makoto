"""Four independent decisions over one claim projection; see DESIGN.md."""
from .claims import claims, literals
from .precision import contains
from .borrowed import receipt
from .switch import names_change, edited_forms
from .points import other_point, claim_locations, located, related_readings
from .observed import effects


def finding(rule, subject, missing):
    return {'rule': rule, 'family': rule,
            'shape': {'a': 'lineage', 'b': 'spec', 'c': 'other point', 'd': 'switch'}[rule],
            'subject': subject, 'missing': missing}


def literal_readings(ledger, span, event):
    # Origin and time are different evidence: c alone decides freshness.
    given = [{'q': ledger.q, 'subjects': [], 'texts': [t], 'source': True, 'tool_use_id': 'user prompt'}
             for t in ledger.given if contains(t, span.text, span.kind)]
    return given + [r for r in ledger.readings if r['source'] and (
        any(any(s.text == span.text for s in literals(t)) if span.kind == 'digit' else contains(t, span.text, span.kind) for t in r['texts']) or
        span.kind in ('path', 'url') and (ledger.subject(span.text, event) in r['subjects'] or any(
            p['tool_use_id'] == r['tool_use_id'] and p['path'] == located(span.text, event)[0]
            for p in ledger.point_readings)))]


def lineage(ledger, event, text, spans):
    return [finding('a', s.text, 'ANSWER FROM ITS OWN ANSWER: read an original artifact containing this literal before this step')
            for s in spans if not literal_readings(ledger, s, event)
            and not (s.kind in ('path', 'url') and any(
                ledger.subject(s.text, event) in r['subjects'] for r in ledger.readings))]


def spec(ledger, event, text, spans):
    findings = []
    for spelling, (path, point) in claim_locations(event, ledger):
        if spelling not in {s.text for s in spans}:
            continue
        related = related_readings(ledger, path)
        if not related:
            findings.append(finding('b', spelling, 'THING NOT READ: read the named subject itself; typed input and a mention in another artifact are not readings of it'))
    for definition in ledger.definitions:
        if not contains(text, definition['subject']):
            continue
        required = ledger.subject(definition['definition'], event)
        if not any(required in r['subjects'] for r in ledger.readings if r['source']):
            findings.append(finding('b', definition['definition'], 'DEFINITION NOT READ: read this subject definition before using it'))
    return findings


def other(ledger, event, text, spans):
    findings = other_point(ledger, event)
    located = {s for s, _ in claim_locations(event, ledger)}
    for span in spans:
        if span.text in located:
            continue
        readings = literal_readings(ledger, span, event)
        if readings and not any(ledger.fresh(r) for r in readings):
            findings.append(finding('c', span.text, 'OTHER PLACE OR TIME: read this literal from its source after its last change'))
    return findings


def switch(ledger, event, text, spans):
    findings = []
    changes = ledger.changed_code()
    # Reading existing executable content establishes a subject even without an
    # edit. A read is not execution; an unchanged subject has last-change zero.
    for r in ledger.readings:
        if r['tool'] == 'WebFetch':
            continue
        for subject in r['subjects']:
            if subject in changes or not subject.startswith('file:'):
                continue
            form = edited_forms(dict(event, tool_name='Write', tool_input={'file_path': subject[5:], 'content': '\n'.join(r['texts'])}), subject[5:])
            if form and not (form.get('record') and form.get('data')):
                form['q'] = ledger.mutations.get(subject, 0)
                changes[subject] = form
    for change in changes.values():
        # Existing, unedited programs are selected only when named. Shipping
        # session edits keeps the established commit/final implicit selection.
        selected = names_change(event, change)
        if change['subject'] not in ledger.changed_code():
            selected = any(contains(text, alias) for alias in change['aliases'])
        if selected and not ledger.run_witnesses(change):
            findings.append(finding('d', change['display'], 'UNRUN CHANGE: run it and read the output before this step'))
    return findings


def evaluate(ledger, event, adapter='inferred'):
    if adapter != 'inferred':
        raise ValueError('adapter must be inferred')
    text, spans = claims(ledger, event)
    findings = []
    for check in (lineage, spec, other, switch):
        findings.extend(check(ledger, event, text, spans))
    findings = list({(f['rule'], f['subject']): f for f in findings}.values())
    trace = [r['tool_use_id'] for r in ledger.readings]
    snapshot = [] if findings or not trace else [receipt(text, trace, 'makoto2.precision/form-v1')]
    for change in ledger.changed_code().values():
        runs = ledger.run_witnesses(change)
        if names_change(event, change) and runs:
            snapshot.append(receipt(change['display'], [r['tool_use_id'] for r in runs], 'makoto2.switch/execution-v1'))
    snapshot.extend({'span': e['subject'], 'kind': 'path', 'output': True} for e in effects(event))
    return findings, snapshot
