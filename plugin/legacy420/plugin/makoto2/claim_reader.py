"""One deterministic output adapter: subject, value tokens, kind and point.

Only asserted clauses are claims. Questions, proposals, and explicitly unpaid
clauses do not assert a verified property. Token tables are language grammar,
never fixture identities. Legacy verdict fields share this same adapter.
"""
import json
import re
from makoto2 import observed

VALUE = re.compile(r'(?<!\w)(?:\d+(?:\.\d+)?%?|[0-9a-f]{7,64})(?!\w)|["“]([^"”\n]+)["”]', re.I)
UNPAID = re.compile(r'\b(?:unverified|unknown|not verified|not confirmed|not current evidence|until rerun|cannot confirm)\b', re.I)
PROPOSED = re.compile(r'^\s*(?:I (?:will|plan|intend)|(?:please )?(?:run|read|check|verify)\b|TODO\b)', re.I)


def output_text(event):
    if event.get('hook_event_name') in ('Stop', 'SubagentStop'):
        return observed.text_of(event)
    ti = event.get('tool_input') or {}
    if event.get('tool_name') in ('Write', 'Edit'):
        return str(ti.get('content', ti.get('new_string', ti.get('new', ''))))
    return ''


def value_tokens(text):
    return tuple(dict.fromkeys(m.group(1) or m.group(0) for m in VALUE.finditer(text)))


def _read_claims(record, event):
    # Import lazily: family_spec owns the compatibility verdict grammar.
    from makoto2.family_spec import claims, verifier_keys
    explicit = event.get('claim')
    if isinstance(explicit, dict):
        value = dict(explicit)
        value.setdefault('values', value_tokens(str(value.get('number', value.get('value', '')))))
        value.setdefault('falsifier', value.get('subject') in verifier_keys(record))
        return [] if value.get('unverified') else [value]
    result = []
    text = output_text(event)
    # A qualification binds the entire sentence, including its semicolon clauses.
    for sentence in re.split(r'(?<=[.!?])\s+|\n', text):
        if not sentence.strip() or sentence.rstrip().endswith('?') or UNPAID.search(sentence) or PROPOSED.search(sentence):
            continue
        if re.search(r'\b(?:must|should|until|expires|discharge|on pass)\b', sentence, re.I):
            continue
        legacy = [c._asdict() for c in claims(sentence, record)]
        values = value_tokens(sentence)
        paths = sorted(observed._text_objects(sentence, event.get('cwd', '')))
        subject = paths[0] if paths else re.split(r'\b(?:is|are|has|have|uses?|contains?|shows?)\b|:', sentence, maxsplit=1)[0].strip(' .')
        kind = 'property'
        if re.search(r'\b(?:branch|case|mode|condition|fallback|rejects?|den(?:y|ies)|catches?|recovery|combination)\b', sentence, re.I):
            kind = 'condition'
        if legacy:
            for value in legacy:
                value.update(values=values, text=sentence, point='current' if re.search(r'\b(?:current|now|live|production|landed)\b', sentence, re.I) else '',
                             subject=value.get('subject') or (subject if value.get('kind') not in ('done', 'running', 'absent', 'clean', 'cannot', 'shipped') else ''))
                result.append(value)
        elif kind == 'condition' or values or re.search(r'\b(?:is|are|has|have|uses?|contains?|shows?|handles?|permits?|prohibits?|required|safe|compliant|verified|supported|operating|compatible|proven|preserved)\b', sentence, re.I):
            result.append(dict(kind=kind, subject=subject, values=values, text=sentence, names=False, falsifier=False,
                               point='current' if re.search(r'\b(?:current|now|live|production|landed)\b', sentence, re.I) else ''))
    return result


def read_claims(record, event):
    """Parse once per immutable record/event pair for all four owners."""
    key = json.dumps(event, sort_keys=True, default=str)
    cache = getattr(record, '_claim_cache', None)
    if cache is None or cache[0] != key:
        cache = (key, _read_claims(record, event))
        record._claim_cache = cache
    return [dict(claim) for claim in cache[1]]


def named_failure_identities(identities, text):
    """A unique parameter label can name a recorded parametrized failure."""
    identities = set(identities)
    tokens = {token.rstrip('.:/-') for token in re.findall(r'[\w./:-]+(?:\[[^\]\n]+\])?', text)}
    parameters = {}
    for identity in identities:
        match = re.search(r'\[([^\]\n]+)\]$', identity)
        if match:
            parameters.setdefault(match.group(1), set()).add(identity)
    named = set()
    for identity in identities:
        leaf = identity.rsplit('::', 1)[-1]
        stem = identity.split('::', 1)[0].rsplit('/', 1)[-1].rsplit('.', 1)[0]
        if tokens & {identity, leaf, leaf.split('[', 1)[0], stem}:
            named.add(identity)
    for parameter, owners in parameters.items():
        if len(owners) == 1 and parameter in tokens:
            named.update(owners)
    return named
