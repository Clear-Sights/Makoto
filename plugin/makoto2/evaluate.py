"""Four presence predicates, one dispatch. Values are never compared."""
from .obligations import ADAPTERS, ContractError
from .provenance import point_matches


def spec(ledger, event, obligation):
    defs = [d for d in ledger.definitions if d['id'] == obligation.get('definition_id') and
            d['subject'] == ledger.subject(obligation['subject'], event) and
            d.get('selector', 'content') == obligation.get('selector', 'content') and
            (obligation.get('definition_revision', obligation.get('revision')) is None or d.get('revision') == obligation.get('definition_revision', obligation.get('revision')))]
    if not defs:
        return 'register the held definition ' + str(obligation.get('definition_id'))
    if not ledger.matching(obligation, event):
        return 'read the subject under its held definition'


def other(ledger, event, obligation):
    if obligation.get('recorded_freshness'):
        from .surface import fresh
        if not fresh(ledger, ledger.subject(obligation['subject'], event)):
            return 'no reading after the last recorded mutation at its destination'
        return None
    points = obligation.get('points')
    if not isinstance(points, list) or len(points) != 2 or any(not isinstance(p, dict) or not p for p in points):
        raise ContractError('OTHER POINT requires two exact point records')
    first = [r for r in ledger.matching(obligation, event, historical=True) if point_matches(r['point'], points[0])]
    second = [r for r in ledger.matching(obligation, event) if point_matches(r['point'], points[1]) and r['q'] > obligation.get('after_sequence', -1)]
    if not any(a['receipt_id'] != b['receipt_id'] for a in first for b in second):
        return 'read the same subject at both required points: ' + str(points)


def switch(ledger, event, obligation):
    if obligation.get('command'):
        # Restricted native cat binds command, input, subject and response;
        # general commands require trusted invocation + read receipts.
        for reading in ledger.matching(obligation, event):
            if reading.get('command') == obligation['command'] and reading['pre_q'] < reading['q'] and reading['command_context'] == [event.get('cwd'), event.get('makoto', {}).get('place', {})]:
                return None
        return 'feed the exact input with ' + obligation['command'] + ', then read its corresponding response'
    if not obligation.get('input_sha256'):
        raise ContractError('SWITCH needs a host-owned exact input digest and selector')
    subject = ledger.subject(obligation['subject'], event)
    for reading in ledger.matching(obligation, event):
        if reading['invocation_subject'] == subject and reading['invocation_selector'] == obligation.get('selector', 'content') and reading['input_sha256'] == obligation['input_sha256'] and reading['pre_q'] < reading['q']:
            return None
    return 'feed the required input ' + obligation['input_sha256'] + ', then read that invocation response'


def lineage(ledger, event, obligation):
    if not any(r['role'] == 'source' and r['turn'] == ledger.turn and not r.get('producer') and (not obligation.get('trace_value') or obligation['trace_value'] in r['values']) for r in ledger.matching(obligation, event)):
        return 'read the original source this turn before writing or answering'


PREDICATES = {'SPEC': spec, 'OTHER_POINT': other, 'SWITCH': switch, 'LINEAGE': lineage}


def evaluate(ledger, event, adapter):
    obligations = ADAPTERS[adapter](event, ledger)
    findings = []
    snapshots = []
    for obligation in obligations:
        shape = obligation.get('shape')
        if shape not in PREDICATES or 'subject' not in obligation:
            raise ContractError('unknown shape or missing exact subject')
        missing = PREDICATES[shape](ledger, event, obligation)
        if missing:
            findings.append({'family': shape, 'subject': ledger.subject(obligation['subject'], event), 'missing': missing})
        candidates = ledger.matching(obligation, event, historical=shape == 'OTHER_POINT')
        if shape == 'LINEAGE':
            candidates = [r for r in candidates if r['role'] == 'source' and r['turn'] == ledger.turn and not r.get('producer')]
        snapshots.append({'obligation': obligation, 'reading_receipt_ids': [r['receipt_id'] for r in candidates]})
    return findings, snapshots
