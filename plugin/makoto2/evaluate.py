"""Four pre-step holds derived only from literal session observations."""
import os
import re
from .precision import extract, names, contains
from .observed import text_of, effects
from .borrowed import receipt
from .switch import names_change


def evaluate(ledger, event, adapter='inferred'):
    if adapter != 'inferred':
        raise ValueError('adapter must be inferred')
    text = text_of(event)
    readings = ledger.source_readings()
    findings, snapshot = [], []
    spans = extract(text)
    name_spans = names(text, shell=event.get('tool_name') == 'Bash')
    output_subjects = ledger.written | {ledger.subject(r['subject'], event) for r in effects(event)}
    output_ranges = []
    # Whitespace in an output filename can split lexical tokens. Exempt those
    # slices only within a complete output path, with exact token boundaries.
    for subject in output_subjects:
        if subject.startswith('file:') and ' ' in subject:
            absolute = subject[5:]
            relative = os.path.relpath(absolute, event.get('cwd') or os.getcwd())
            for path in {absolute, relative, './' + relative}:
                pattern = r'(?<![\w/\\.@:+~%#?=&$!*|-])' + re.escape(path) + r'(?![\w/\\.@:+~%#?=&$!*|-])'
                output_ranges.extend(m.span() for m in re.finditer(pattern, text))

    def output_name(span):
        return span.kind == 'path' and ledger.subject(span.text, event) in output_subjects or any(start <= span.start and span.end <= end for start, end in output_ranges)

    if not readings:
        span = spans[0].text if spans else text
        findings.append({'rule': 'a', 'family': 'a', 'shape': 'lineage', 'subject': span,
                         'missing': 'ANSWER FROM ITS OWN ANSWER: read an original artifact before this step; assistant text and files this session wrote do not clear it'})
    # Rule a asks whether an original artifact was read. It does not require
    # a derived result or repeated answer to occur verbatim in that artifact.
    # Exact unread names remain governed independently by rule b.
    for span in name_spans:
        if output_name(span):
            snapshot.append({'span': span.text, 'kind': span.kind, 'output': True})
            continue
        witnesses = ledger.witnesses(span.text, span.kind)
        if not witnesses:
            findings.append({'rule': 'b', 'family': 'b', 'shape': 'spec', 'subject': span.text,
                             'missing': 'NAMED WITHOUT READING: read a source whose tool input or response contains these exact characters; a different spelling or stale reading does not clear it'})
        else:
            snapshot.append({'span': span.text, 'kind': span.kind,
                             'reading_receipt_ids': [w.get('tool_use_id', 'user prompt') for w in witnesses]})
    external = [s.text for s in spans + name_spans if s.kind in ('url', 'external-package')]
    # Host-classified public projects are checked by the same literal sweep.
    external += [s for s in ledger.external + event.get('makoto', {}).get('external_subjects', []) if contains(text, s)]
    for span in dict.fromkeys(external):
        if not ledger.fetched(span):
            findings.append({'rule': 'c', 'family': 'c', 'shape': 'other point', 'subject': span,
                             'missing': 'DID NOT LOOK ONLINE: fetch or search this exact external subject with WebFetch, WebSearch or a Bash network call in this turn'})
    for change in ledger.changed_code().values():
        if not names_change(event, change):
            continue
        runs = ledger.run_witnesses(change)
        readbacks = ledger.readback_witnesses(change)
        if not runs and not readbacks:
            findings.append({'rule': 'd', 'family': 'd', 'shape': 'switch',
                             'subject': change['display'],
                             'missing': 'UNRUN CHANGE: run it and read the output before this step'})
        else:
            witnesses = runs or readbacks
            snapshot.append(receipt(change['display'], [run['tool_use_id'] for run in witnesses],
                                    'makoto2.switch/execution-v1' if runs else 'makoto2.switch/readback-v1'))
    if not findings:
        snapshot.append(receipt(text, [r['tool_use_id'] for r in readings], 'makoto2.precision/form-v1'))
    return list({(f['rule'], f['subject']): f for f in findings}.values()), snapshot
