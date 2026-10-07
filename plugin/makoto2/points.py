"""Located readings compared by literal path and explicit point coordinates."""
import re
import shlex
from urllib.parse import urlsplit

from .observed import WRITERS, programs, reading_subjects, network_targets
from .paths import normalized_path, program_name
from .precision import names


# These are coordinate syntax, not words used to classify a subject's meaning.
COORDINATE = re.compile(r'\b(host|branch|environment|copy|target|mount)(?:[=:]\s*|\s+)[`\"\x27]?([\w./@-]+)')


def coordinates(text):
    return dict(COORDINATE.findall(text))


def located(value, event, point=None):
    point = dict(point or {})
    if value.startswith(('http://', 'https://')):
        url = urlsplit(value)
        return (url.path or '/', tuple(sorted(dict(point, host=url.netloc, scheme=url.scheme).items())))
    # git's revision:path and ssh's host:/path retain their explicit coordinate.
    match = re.fullmatch(r'([^:/\\\s]+):(.+)', value)
    if match and not re.match(r'^[A-Za-z]:[/\\]', value):
        qualifier, value = match.groups()
        point['host' if value.startswith('/') else 'branch'] = qualifier
    return normalized_path(value.removeprefix('file:'), event.get('cwd') or '/'), tuple(sorted(point.items()))


def read_locations(pre):
    point = dict(pre.get('makoto', {}).get('place', {}))
    point = {k: str(v) for k, v in point.items()}
    subjects = reading_subjects(pre)
    if pre.get('tool_name') != 'WebSearch':
        subjects += [s for s in network_targets(pre, {}) if s.startswith(('https://', 'http://'))]
    if pre.get('tool_name') == 'Bash':
        for words in programs(pre):
            if program_name(words[0]) == 'git' and len(words) > 2 and words[1] == 'show':
                subjects += [w for w in words[2:] if ':' in w and not w.startswith('-')]
            elif program_name(words[0]) == 'ssh' and len(words) > 2 and not words[1].startswith('-'):
                remote = dict(pre, tool_input={'command': ' '.join(words[2:])})
                subjects += reading_subjects(remote)
                point['host'] = words[1]
        point.update(coordinates(pre.get('tool_input', {}).get('command', '')))
    return [located(s, pre, point) for s in subjects if isinstance(s, str)]


def claim_locations(event, ledger=None):
    """Locate only authored claim paths, never writer destinations or old text."""
    from .claims import authored_text, claims, literals
    text, spans = claims(ledger, event) if ledger is not None else (authored_text(event), literals(authored_text(event)))
    result = []
    for span in spans:
        if span.kind not in ('path', 'url'):
            continue
        start = text.rfind('\n', 0, span.start) + 1
        end = text.find('\n', span.end)
        line = text[start:end if end >= 0 else len(text)]
        if any(start + m.start() <= span.start < start + m.end() for m in COORDINATE.finditer(line)):
            continue
        result.append((span.text, located(span.text, event, coordinates(line))))
    return result


def related_readings(ledger, path, *, runs=False):
    """Same subject identity or a host-recorded copy relation, never basename."""
    paths = {path}
    while True:
        expanded = paths | {p for pair in ledger.point_aliases if paths.intersection(pair) for p in pair}
        if expanded == paths:
            records = list(ledger.point_readings)
            if runs:
                records += [dict(path=p, point=point, started=r['started'], tool_use_id=r['tool_use_id'])
                            for r in ledger.executions for p, point in r.get('locations', [])]
            return [r for r in records if r['path'] in paths]
        paths = expanded


def other_point(ledger, event):
    findings = []
    for spelling, (path, point) in claim_locations(event, ledger):
        related = related_readings(ledger, path, runs=True)
        if not related:
            continue
        subject = ledger.subject(path, event) if not spelling.startswith(('http://', 'https://')) else spelling
        last_change = ledger.mutations.get(subject, 0)
        pending = any(subject in targets for targets in ledger.reservations.values())
        if not pending and any(r['path'] == path and r['point'] == point
                               and r['started'] > last_change for r in related):
            continue
        findings.append({'rule': 'c', 'family': 'c', 'shape': 'other point', 'subject': spelling,
                         'missing': 'OTHER PLACE OR TIME: read this same subject at the named point after its last change'})
    return findings
