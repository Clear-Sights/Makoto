"""Three pre-step holds derived only from literal session observations."""
import os
import re
from .precision import extract, names, contains
from .observed import text_of, effects
from .borrowed import receipt


def evaluate(ledger, event, adapter='inferred'):
    if adapter != 'inferred':
        raise ValueError('adapter must be inferred')
    text = text_of(event)
    readings = ledger.source_readings()
    findings, snapshot = [], []
    spans = extract(text)
    name_spans = names(text)
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

    output_spans = {(s.start, s.end) for s in spans if any(start <= s.start and s.end <= end for start, end in output_ranges)}
    output_spans.update((s.start, s.end) for s in name_spans if output_name(s))
    # A path-only final may literally repeat the writer's target. It references
    # the output, rather than copying the answer stored in that output.
    output_reference = any(s.text == text.strip(' \n\t`"\x27“”‘’') and output_name(s) for s in name_spans)
    output_reference |= any(not text[:start].strip(' \n\t`"\x27“”‘’') and not text[end:].strip(' \n\t`"\x27“”‘’') for start, end in output_ranges)
    source_reference = any(s.text == text.strip(' \n\t`"\x27“”‘’') and any(any(contains(t, s.text, s.kind) for t in r['texts']) for r in readings) for s in name_spans)
    if not readings:
        span = spans[0].text if spans else text
        findings.append({'rule': 'a', 'family': 'a', 'subject': span,
                         'missing': 'ANSWER FROM ITS OWN ANSWER: read an original artifact before this step; assistant text and files this session wrote do not clear it'})
    if text and readings and not (output_reference or source_reference) and not any(contains(given, text) for given in ledger.given) and any(contains(own, text) for own in ledger.own) and not any(any(contains(t, text) for t in r['texts']) for r in readings):
        findings.append({'rule': 'a', 'family': 'a', 'subject': text, 'missing': 'ANSWER FROM ITS OWN ANSWER: read an original artifact containing this text before copying the session answer'})
    for span in spans:
        if (span.start, span.end) not in output_spans and any(contains(own, span.text) for own in ledger.own) and not any(contains(given, span.text) for given in ledger.given) and not any(any(contains(t, span.text) for t in r['texts']) for r in readings):
            findings.append({'rule': 'a', 'family': 'a', 'subject': span.text, 'missing': 'ANSWER FROM ITS OWN ANSWER: read an original artifact containing these exact characters; own output cannot clear it'})
    for span in name_spans:
        if output_name(span):
            snapshot.append({'span': span.text, 'kind': span.kind, 'output': True})
            continue
        witnesses = ledger.witnesses(span.text, span.kind)
        if not witnesses:
            findings.append({'rule': 'b', 'family': 'b', 'subject': span.text,
                             'missing': 'NAMED WITHOUT READING: read a source whose tool input or response contains these exact characters; a different spelling or stale reading does not clear it'})
        else:
            snapshot.append({'span': span.text, 'kind': span.kind,
                             'reading_receipt_ids': [w.get('tool_use_id', 'user prompt') for w in witnesses]})
    external = [s.text for s in spans + name_spans if s.kind in ('url', 'external-package')]
    # Host-classified public projects are checked by the same literal sweep.
    external += [s for s in ledger.external + event.get('makoto', {}).get('external_subjects', []) if contains(text, s)]
    for span in dict.fromkeys(external):
        if not ledger.fetched(span):
            findings.append({'rule': 'c', 'family': 'c', 'subject': span,
                             'missing': 'DID NOT LOOK ONLINE: fetch or search this exact external subject with WebFetch, WebSearch or a Bash network call in this turn'})
    if not findings:
        snapshot.append(receipt(text, [r['tool_use_id'] for r in readings], 'makoto2.precision/form-v1'))
    return list({(f['rule'], f['subject']): f for f in findings}.values()), snapshot
