"""One form projection for dependent-step claims (DESIGN D1–D11)."""
import ast
import re
import shlex
from .paths import path_spellings
from .observed import WRITERS, FINAL
from .precision import Span, names, contains, DELIMITED, VERSIONED


def authored_text(event):
    if event['hook_event_name'] in FINAL:
        return event.get('last_assistant_message', '')
    ti = event.get('tool_input', {})
    if event.get('tool_name') in WRITERS:
        return '\n'.join(str(ti[k]) for k in ('content', 'new_string', 'new_source') if k in ti) + '\n' + '\n'.join(e.get('new_string', '') for e in ti.get('edits', []))
    if event.get('tool_name') == 'Bash':
        try:
            words = shlex.split(ti.get('command', ''))
        except ValueError:
            return ''
        return '\n'.join(words[i + 1] for i, w in enumerate(words[:-1]) if w == '--message' or re.fullmatch(r'-[A-Za-z]*m', w)) + '\n' + '\n'.join(w.split('=', 1)[1] for w in words if w.startswith('--message='))
    return ''


def literals(text):
    result = [s for s in names(text) if s.kind != 'external-package']
    for match in re.finditer(r'(?m)^#!\s*(\S+)', text):
        start, end = match.span(1)
        result = [s for s in result if not (s.start < end and start < s.end)]
        result.append(Span(match[1], start, end, 'path'))
    for match in re.finditer(r'(?<!\w)\d{4}-\d{2}-\d{2}T[\d:.]+Z?(?!\w)', text):
        result.append(Span(match.group(), *match.span(), 'identifier'))
    for match in VERSIONED.finditer(text):
        separator = text[match.end('package'):match.start('version')]
        if any(operator in separator for operator in ('@', '==', '>=', '<=', '~=')):
            result.append(Span(match['package'], *match.span('package'), 'package-name'))
        if not any(s.start <= match.start('version') and match.end('version') <= s.end for s in result):
            result.append(Span(match['version'], *match.span('version'), 'version-component'))
    for match in re.finditer(r'(?<![\w./])[+-]?\d+(?:\.\d+)?(?:\s*(?:ms|s|kg|g|MB|GB|%))?(?![\w/]|\.\w)', text):
        if not any(s.start <= match.start() < s.end for s in result):
            result.append(Span(match.group(), *match.span(), 'digit'))
    for match in DELIMITED.finditer(text):
        if match.lastgroup in ('fence', 'tilde'):
            continue
        start, end = match.span(match.lastgroup)
        if not any(start <= s.start and s.end <= end for s in result):
            result.append(Span(text[start:end], start, end, 'delimited'))
    return sorted(result, key=lambda s: (s.start, s.end))


def claims(ledger, event):
    text = authored_text(event)
    spans = literals(text)
    # A known space-containing path remains one literal, including unquoted
    # references. Its component filenames cannot become separate subjects.
    known = ledger.written | {s for r in ledger.readings for s in r['subjects']}
    for subject in known:
        if not subject.startswith('file:') or ' ' not in subject:
            continue
        for spelling in path_spellings(subject[5:], event.get('cwd') or '/'):
            for match in re.finditer(r'(?<![\w/\\.])' + re.escape(spelling) + r'(?![\w/\\.])', text):
                spans = [s for s in spans if not (match.start() <= s.start and s.end <= match.end())]
                spans.append(Span(spelling, *match.span(), 'path'))
    spans.sort(key=lambda s: (s.start, s.end))
    if event.get('tool_name') not in WRITERS:
        return text, spans
    # A syntactically complete program defines new names/values. References to
    # earlier recorded things and external locations still make claims in it.
    try:
        tree = ast.parse(text)
        program = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign, ast.Import, ast.ImportFrom))
                      or isinstance(n, ast.Expr) and isinstance(n.value, (ast.Dict, ast.List, ast.Tuple))
                      for n in tree.body)
    except SyntaxError:
        program = False
    if not program:
        return text, spans
    prior = ledger.given + ledger.own + [t for r in ledger.readings + ledger.inputs for t in r['texts']]
    return text, [s for s in spans if s.kind in ('path', 'url', 'external-package') or any(contains(t, s.text, s.kind) for t in prior)]
