"""Three pre-step holds derived only from literal session observations."""
from .precision import extract, contains
from .observed import text_of
from .borrowed import receipt


def evaluate(ledger, event, adapter='inferred'):
    if adapter != 'inferred':
        raise ValueError('adapter must be inferred')
    text = text_of(event)
    readings = ledger.source_readings()
    findings, snapshot = [], []
    spans = extract(text)
    if not readings:
        span = spans[0].text if spans else text
        findings.append({'rule': 'a', 'family': 'a', 'subject': span,
                         'missing': 'ANSWER FROM ITS OWN ANSWER: read an original artifact before this step; assistant text and files this session wrote do not clear it'})
    if text and readings and not any(contains(given, text) for given in ledger.given) and any(contains(own, text) for own in ledger.own) and not any(any(contains(t, text) for t in r['texts']) for r in readings):
        findings.append({'rule': 'a', 'family': 'a', 'subject': text, 'missing': 'ANSWER FROM ITS OWN ANSWER: read an original artifact containing this text before copying the session answer'})
    for span in spans:
        witnesses = ledger.witnesses(span.text, span.kind)
        if any(contains(own, span.text) for own in ledger.own) and not any(contains(given, span.text) for given in ledger.given) and not any(any(contains(t, span.text) for t in r['texts']) for r in readings):
            findings.append({'rule': 'a', 'family': 'a', 'subject': span.text, 'missing': 'ANSWER FROM ITS OWN ANSWER: read an original artifact containing these exact characters; own output cannot clear it'})
        if not witnesses:
            findings.append({'rule': 'b', 'family': 'b', 'subject': span.text,
                             'missing': 'NAMED WITHOUT READING: read a source whose tool input or response contains these exact characters; a different spelling or stale reading does not clear it'})
        else:
            snapshot.append({'span': span.text, 'kind': span.kind,
                             'reading_receipt_ids': [w.get('tool_use_id', 'user prompt') for w in witnesses]})
    external = [s.text for s in spans if s.kind in ('url', 'external-package')]
    # Host-classified public projects are checked by the same literal sweep.
    external += [s for s in ledger.external + event.get('makoto', {}).get('external_subjects', []) if contains(text, s)]
    for span in dict.fromkeys(external):
        if not ledger.fetched(span):
            findings.append({'rule': 'c', 'family': 'c', 'subject': span,
                             'missing': 'DID NOT LOOK ONLINE: fetch or search this exact external subject with WebFetch, WebSearch or a Bash network call in this turn'})
    if not findings:
        snapshot.append(receipt(text, [r['tool_use_id'] for r in readings], 'makoto2.precision/form-v1'))
    return list({(f['rule'], f['subject']): f for f in findings}.values()), snapshot
