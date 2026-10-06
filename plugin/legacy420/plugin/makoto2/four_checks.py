"""Four record comparisons over the shared claim adapter.

These checks never consult unrecorded current bytes. A reading's point and
provenance come from its settled event; a write invalidates rather than pays a
source reading. Residual structural predicates live in the family modules.
"""
import ast
import json
import os
import re
from makoto2 import observed
from makoto2.claim_reader import read_claims, value_tokens
from makoto2.family_spec import finding

RELAY = re.compile(r'\b(?:answer|memo|receipt|digest|sweep|audit.note|memory|summary)\b', re.I)
CHANGE = re.compile(r'\b(?:updated|changed|recreated|replaced|removed|refresh(?:ed)?|invalidated)\b', re.I)
WORDS = re.compile(r'[a-z][a-z_-]+', re.I)
GRAMMAR = frozenset('the a an is are was were has have current now old prior previous source recorded reading value maximum minimum approved cost of for to from in at as by this that it its and or with after before'.split())


def terms(text):
    return set(WORDS.findall(text.lower())) - GRAMMAR


def readings(record):
    """Adapt the shared provenance ledger for the family comparisons."""
    from makoto2.provenance import trace_for
    trace = trace_for(record, observed)
    return [dict(seq=r.seq, identities={r.source}, text=r.text,
                 values=set(value_tokens(r.text)), terms=terms(r.text), relay=not r.original)
            for r in trace.readings], trace.invalidated


def emit(entries, subject, missing, family):
    return finding(entries, subject, 'missing reading: ' + missing + ' [' + str(subject) + ']', family)


def lineage(record, event, cfg):
    from makoto2 import family_lineage
    obligations = (
        (family_lineage.lineage_absence, ('C2', 'B32'), 'original independent absence probe', 'R05'),
        (family_lineage.hook_lineage_refs, ('A2', 'G1', 'H1', 'H4', 'H5'), 'cited original source', 'R08'),
        (family_lineage.lineage_drift, ('D4', 'F7', 'F10', 'H2'), 'original source at the latest version', 'L.drift'),
    )
    for extract, entries, missing, row in obligations:
        for subject in extract(record, event, observed):
            yield emit(entries, subject, missing, row)
    from makoto2.provenance import trace_for, violations
    trace = trace_for(record, observed)
    for subject in violations(record, event, observed):
        sources = sorted({r.source for r in trace.origins(subject)
                          if not r.original or not trace.current(r)})
        missing = 'latest original-source observation'
        if sources:
            missing += ' of ' + ', '.join(sources)
        yield emit(('H1', 'H2', 'H4', 'F10'), subject, missing, 'LINEAGE')


def spec(record, event, cfg):
    sources, _ = readings(record)
    for claim in read_claims(record, event):
        text = claim.get('text', '')
        # A measured value carries a unit; equal numerals do not equate units.
        for source in sources:
            unit = re.search(r'\bunit\s*=\s*(\w+)', source['text'])
            metric = re.search(r'\bmetric\s*=\s*([\w-]+)', source['text'])
            if metric:
                metric_words = set(re.split(r'[_-]', metric.group(1).lower()))
                if not metric_words <= set(re.findall(r'\w+', text.lower())):
                    continue
            if unit and set(claim.get('values', ())) & source['values']:
                declared = re.findall(r'\b(?:milliseconds|seconds|minutes|hours|bytes|kilobytes|megabytes)\b', text, re.I)
                if declared and unit.group(1).lower() not in [x.lower() for x in declared]:
                    yield emit(('A5',), claim['subject'], 'value with its measured unit', 'SPEC')


    # Definitions supplied by the operator are numeric relations. Compare the
    # written assertion's operator/value against the held relation, independent
    # of file names, function names, or the number's spelling.
    definition = ' '.join(getattr(record, 'user_texts', ()))
    ti = event.get('tool_input') or {}
    written = ti.get('content', ti.get('new_string', ''))
    if event.get('tool_name') in ('Write', 'Edit'):
        try:
            tree = ast.parse(written)
        except (SyntaxError, TypeError):
            tree = None
        if tree:
            comparisons = [n for n in ast.walk(tree) if isinstance(n, ast.Compare)]
            exact = re.search(r'\b(?:exactly|pin\b[^.]*?at)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b', definition, re.I)
            direction = (re.search(r'\b(?:at least|smaller[^.]*better|lower[^.]*latency)\b', definition, re.I))
            for node in comparisons:
                if len(node.ops) != 1:
                    continue
                if exact and isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Name) and node.left.func.id == 'len' and not isinstance(node.ops[0], ast.Eq):
                    yield emit(('B23',), ast.unparse(node.left), 'exact equality to the held inventory definition', 'SPEC')
                if direction and isinstance(node.comparators[0], ast.Constant):
                    lower = bool(re.search(r'\b(?:smaller|lower)\b', definition, re.I))
                    wrong = isinstance(node.ops[0], (ast.Gt, ast.GtE)) if lower else isinstance(node.ops[0], (ast.Lt, ast.LtE))
                    if wrong:
                        yield emit(('C6',), ast.unparse(node.left), 'assertion in the defined acceptance direction', 'SPEC')
        # A structured retry plan has one total duration, including backoff.
        try:
            plan = json.loads(written)
        except (ValueError, TypeError):
            plan = None
        budgets = re.findall(r'\b(\d+)[ -]second(?:s)?\b', definition, re.I)
        if isinstance(plan, dict) and budgets:
            duration = plan.get('attempt_timeout_seconds')
            attempts = plan.get('max_attempts', 1)
            backoff = plan.get('backoff_seconds', 0)
            if all(isinstance(v, (int, float)) for v in (duration, attempts, backoff)) and duration * attempts + backoff * max(0, attempts - 1) > min(map(int, budgets)):
                yield emit(('E11',), 'retry duration', 'whole retry duration within the enclosing deadline', 'SPEC')
    # A fractional measurement and a percentage are different typed values.
    if any(re.search(r'\bfractions?\b', source['text'], re.I) for source in sources):
        for claim in read_claims(record, event):
            for token in claim.get('values', ()):
                if token.endswith('%') and float(token[:-1]) != 0 and any(token[:-1] in source['values'] for source in sources):
                    if not re.search(r'\bfraction\b', claim.get('text', ''), re.I):
                        yield emit(('A5',), claim['subject'], 'percentage converted from the defined fractional scale', 'SPEC')
    # Compare explicit old/new response fields before accepting equivalence.
    for claim in read_claims(record, event):
        text = claim.get('text', '')
        if re.search(r'\bno behaviou?r change\b', text, re.I):
            for source in sources:
                pair = re.search(r'\bold\s*[:=]\s*(\S+).*?\bnew\s*[:=]\s*(\S+)', source['text'], re.I)
                if pair and pair.group(1).rstrip(';') != pair.group(2).rstrip(';'):
                    yield emit(('F14',), claim['subject'], 'equal responses at the compared behavior points', 'SPEC')
        currencies = re.findall(r'\b(?:USD|EUR|GBP|JPY|CAD|AUD|CHF)\b', text)
        if re.search(r'\b(?:within|below|agree)\b', text, re.I) and re.search(r'\b(?:budget|purchase)\b', definition, re.I):
            held = {v for source in sources for v in re.findall(r'\b(?:USD|EUR|GBP|JPY|CAD|AUD|CHF)\b', source['text'])}
            if len(held) > 1 and not any(not source['relay'] and re.search(r'\b(?:conversion|exchange)\b', source['text'], re.I) for source in sources) and not re.search(r'\b(?:convert|conversion|exchange|different|unverified|cannot)\b', text, re.I):
                yield emit(('G3',), claim['subject'], 'both values in a common currency at the boundary', 'SPEC')

    for claim in read_claims(record, event):
        text = claim.get('text', '')
        # A partial or unavailable response has a different verdict type from
        # completion. A nonzero exit alone is not a proof of partial output.
        partial = [o for o in record.obs if o.failed or o.exit not in (None, 0)]
        if claim.get('kind') == 'done' and any(re.search(r'\b(?:timed out|missing trailer|partial|interrupted|before END)\b', o.output, re.I) for o in partial):
            yield emit(('C7',), claim['subject'], 'complete producer response at its terminator', 'SPEC')
        # Per-member definitions retain their grain when a total is quoted.
        universal = re.search(r'\b(?:both|all|each|every)\b', text, re.I)
        target = re.search(r'\b(?:target|meet|delivery)\b', definition, re.I)
        threshold = re.search(r'(\d+(?:\.\d+)?)%', definition)
        if universal and target and threshold and re.search(r'\b(?:meet|complete)\b', text, re.I) and not re.search(r'\b(?:fails?|below|not|different)\b', text, re.I):
            if any(float(v[:-1]) < float(threshold.group(1)) for source in sources for v in source['values'] if v.endswith('%')):
                yield emit(('A7',), claim['subject'], 'every member at the defined target grain', 'SPEC')
        if universal and re.search(r'\bcomplete\b', text, re.I):
            for source in sources:
                try:
                    expected = json.loads(source['text'])
                except ValueError:
                    continue
                if not isinstance(expected, dict) or not expected or not all(isinstance(v, (int, float)) for v in expected.values()):
                    continue
                for later in sources:
                    if later['seq'] <= source['seq']:
                        continue
                    actual = dict((k, float(v)) for k, v in re.findall(r'([\w-]+)\s*=\s*(\d+(?:\.\d+)?)', later['text']))
                    if expected.keys() <= actual.keys() and any(actual[k] != v for k, v in expected.items()):
                        yield emit(('A7',), claim['subject'], 'each inventory member against its held count', 'SPEC')
        if re.search(r'\ball\b.*\bvalid\b', text, re.I):
            if any(re.search(r'\b(?:parsed|discovered|matched)\b[^\n]*?=\s*0\b', source['text'], re.I) for source in sources):
                yield emit(('B2',), claim['subject'], 'nonempty measured population under the universal claim', 'SPEC')
    if (event.get('tool_name') in ('Write', 'Edit') and isinstance(plan, dict)
            and plan.get('evaluation') not in ('unknown', 'not-evaluable', 'unverified')
            and any(v is False and re.search(r'\b(?:present|exists|found)\b', key.replace('_', ' '))
                    for key, v in plan.items())):
        if any(re.search(r'\b(?:unknown|not performed|unavailable)\b', o.output, re.I) for o in record.obs if o.failed or o.exit not in (None, 0)):
            yield emit(('C2',), 'boolean verdict', 'decided presence response rather than unavailable measurement', 'SPEC')

def other_point(record, event, cfg):
    sources, changed = readings(record)
    for claim in read_claims(record, event):
        if claim.get('point') != 'current':
            continue
        text = claim.get('text', '')
        # An explicit source at a different temporal point cannot pay now.
        related = [s for s in sources if len(terms(text) & s['terms']) >= 2]
        if related and all(re.search(r'\b(?:yesterday|previous|before)\b', s['text'], re.I) for s in related):
            yield emit(('D1', 'D4', 'F10'), claim['subject'], 'same subject at the claimed current point', 'OTHER POINT')

    # Points are typed coordinates. A reading at one coordinate does not pay
    # an assertion at a mutually exclusive coordinate of that same dimension.
    coordinates = (
        ('evaluation', {'training': r'\b(?:training|train|tuning)\b', 'independent': r'\b(?:out-of-sample|independent|held.out|separate set)\b'}, ('B18',)),
        ('form', {'source': r'\bsource(?: mode)?\b', 'packaged': r'\b(?:packaged|executable)\b'}, ('D8',)),
        ('platform', {'desktop': r'\bdesktop\b', 'mobile': r'\bmobile\b'}, ('D8',)),
    )
    for claim in read_claims(record, event):
        text = claim.get('text', '')
        if re.search(r'\b(?:not|unverified|fails?|different|incompatible|only)\b', text, re.I):
            continue
        for dimension, points, entries in coordinates:
            asserted = {p for p, regex in points.items() if re.search(regex, text, re.I)}
            if len(asserted) != 1:
                continue
            from makoto2.provenance import tokens, trace_for
            trace = trace_for(record, observed)
            relevant = []
            training_paths = {path for o in record.obs if o.tool == 'Bash'
                              for path in re.findall(r'--train\s+([^\s]+)', o.input.get('command', ''))}
            for o in record.obs:
                if o.tool not in ('Bash', 'Read', 'WebFetch') or o.failed:
                    continue
                response = ' '.join(map(str, o.input.values())) + ' ' + o.output
                shared = (tokens(text) & tokens(response)) - GRAMMAR - set(points)
                shared -= {'mode', 'form', 'platform', 'setting', 'configuration', 'run', 'reading', 'result', 'tested', 'verified'}
                shared = {token for token in shared if not re.fullmatch(r'\d+(?:\.\d+)?%?', token)}
                if not shared:
                    continue
                if o.tool != 'Bash':
                    source = [r for r in trace.readings if r.seq == o.seq and r.original]
                    if not source or (claim.get('values') and not set(claim['values']) & set(value_tokens(o.output))):
                        continue
                point = {p for p, regex in points.items() if re.search(regex, response, re.I)}
                if dimension == 'evaluation' and training_paths:
                    data_paths = re.findall(r'--data\s+([^\s]+)', o.input.get('command', ''))
                    if data_paths:
                        point.add('training' if data_paths[-1] in training_paths else 'independent')
                if point:
                    relevant.append(point)
            if relevant and not any(asserted <= point for point in relevant):
                yield emit(entries, claim['subject'], 'same subject at its asserted ' + dimension + ' point', 'OTHER POINT')


def switch(record, event, cfg):
    # Held test requirements already express the selector. Require its input and
    # returned response together; an intended call is never a witness.
    users = getattr(record, 'user_texts', ())
    requirements = ' '.join(users)
    for claim in read_claims(record, event):
        text = claim.get('text', '')
        if claim.get('kind') == 'pass' and event.get('tool_name') in ('Write', 'Edit'):
            from makoto2 import family_switch
            from makoto2.family_spec import verifier_keys
            paths = cfg.get('named_sets', {}).get('DOC_PATH', ())
            path = str((event.get('tool_input') or {}).get('file_path', ''))
            declared = [pattern for pattern in paths if re.search(pattern, path)]
            if declared:
                adapted = dict(event='Pre', tool=event.get('tool_name'), path=path, claim=claim)
                probes = [dict(verifier=o.input.get('command') in verifier_keys(record)) for o in record.obs]
                unpaid = any(family_switch.switch_doc(adapted, probes, pattern) for pattern in declared)
            else:
                unpaid = not any(o.tool == 'Bash' and not o.failed for o in record.obs)
            if unpaid:
                yield emit(('C11',), claim['subject'], 'deciding run before the written verdict', 'SWITCH')
        selected = re.findall(r'\b(?:unauthorized|invalid|corrupt(?:ion)?|unknown)\b', text, re.I)
        if not selected or not re.search(r'\b(?:verified|catches?|rejects?|deny|denies|correctly)\b', text, re.I):
            continue
        for selector in selected:
            if selector.lower() not in requirements.lower():
                continue
            if not any(not o.failed and selector.lower() in (' '.join(map(str, o.input.values())) + ' ' + o.output).lower()
                       and o.tool not in ('Write', 'Edit', 'Agent', 'Task', 'Read') for o in record.obs):
                yield emit(('B1', 'B20', 'C5'), claim['subject'], 'response to input selecting ' + selector.lower(), 'SWITCH')


def findings(record, event, cfg):
    """Four owners; retained exceptions are measured in RESIDUALS.tsv.

    Core shape findings precede exceptions so an older narrow rule cannot hide
    the source/version failure's register identity.
    """
    from makoto2 import family_spec, family_other, family_switch, family_lineage
    owners = ((spec, family_spec), (other_point, family_other),
              (switch, family_switch), (lineage, family_lineage))
    for check, residual in owners:
        yield from check(record, event, cfg)
    from makoto2 import denominators
    for (check, residual), family in zip(owners, ('SPEC', 'OTHER POINT', 'SWITCH', 'LINEAGE')):
        yield from denominators.findings(record, event, cfg, family)
        findings = residual.findings(record, event, cfg, residual_only=True) if residual is family_lineage else residual.findings(record, event, cfg)
        for item in findings:
            if 'missing reading:' not in item.get('message', ''):
                witness = {'SPEC': 'content or property against its held definition',
                           'OTHER POINT': 'same subject at its claimed point',
                           'SWITCH': 'selected input and its returned response',
                           'LINEAGE': 'latest original source'}[family]
                ids = '/'.join(item.get('entries', ()))
                item = dict(item, message=ids + ': missing reading: ' + witness + ' -- ' + item.get('message', ''))
            yield item
