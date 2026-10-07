"""Located readings compared by literal path and explicit point coordinates."""
import re
import shlex
from urllib.parse import urlsplit

from .observed import WRITERS, programs, reading_subjects
from .paths import normalized_path, program_name
from .precision import names


# These are coordinate syntax, not words used to classify a subject's meaning.
COORDINATE = re.compile(r'\b(host|branch|environment|copy|target)(?:[=:]\s*|\s+)[`\"\x27]?([\w./@-]+)')


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


def claim_locations(event):
    """Writer destinations and replaced text are not claims about their contents."""
    ti = event.get('tool_input', {})
    if event.get('tool_name') in WRITERS:
        text = '\n'.join(str(ti[k]) for k in ('content', 'new_string', 'new_source') if k in ti)
        text += '\n' + '\n'.join(e.get('new_string', '') for e in ti.get('edits', []))
    elif event.get('tool_name') == 'Bash':
        try:
            words = shlex.split(ti.get('command', ''))
        except ValueError:
            return []
        text = '\n'.join(words[i + 1] for i, word in enumerate(words[:-1]) if word in ('-m', '--message'))
        text += '\n' + '\n'.join(w.split('=', 1)[1] for w in words if w.startswith('--message='))
    else:
        text = event.get('last_assistant_message', '')
    result = []
    for line in text.splitlines():
        point = coordinates(line)
        for span in names(line):
            if span.kind not in ('path', 'url'):
                continue
            if any(m.start() <= span.start < m.end() for m in COORDINATE.finditer(line)):
                continue
            result.append((span.text, located(span.text, event, point)))
    return result


def other_point(ledger, event):
    findings = []
    for spelling, (path, point) in claim_locations(event):
        # Equal final path components identify a possible other copy. A wholly
        # unread subject belongs to a/b, never to this extension of c.
        related = [r for r in ledger.point_readings
                   if r['path'].rsplit('/', 1)[-1] == path.rsplit('/', 1)[-1]]
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
