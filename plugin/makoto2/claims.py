"""One form projection for dependent-step claims (DESIGN D1–D11)."""
import ast
import io
import tokenize
import re
import shlex
from .paths import path_spellings
from .observed import WRITERS, FINAL
from .precision import Span, names, contains, DELIMITED, VERSIONED, name_kind


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
    # D6/D9: the name following a coordinate kind is its value literal.
    from .points import COORDINATE
    for match in COORDINATE.finditer(text):
        if match[1] == 'mount':
            continue
        start, end = match.span(2)
        end = start + len(text[start:end].rstrip('.'))
        if start < end and not any(s.start <= start and end <= s.end for s in result):
            result.append(Span(text[start:end], start, end, 'coordinate-name'))
    # D9: separators in a quoted prose value do not name a root directory.
    for match in DELIMITED.finditer(text):
        start, end = match.span(match.lastgroup)
        if re.search(r'\s[/\\]\s', text[start:end]):
            result = [s for s in result if not (start <= s.start and s.end <= end)]
            result.append(Span(text[start:end], start, end, 'delimited'))
    return sorted(result, key=lambda s: (s.start, s.end))


def claims(ledger, event):
    text = authored_text(event)
    spans = literals(text)
    # D7/D18: the grammatical subject of an acceptance assertion is a
    # subject even when its identifier consists of ordinary words.
    for match in re.finditer(r'(?m)^(?:#\s*|[Tt]he\s+)?([A-Za-z][A-Za-z -]*?)\s+accepts\b', text):
        start, end = match.span(1)
        if not any(start <= s.start and s.end <= end for s in spans):
            spans.append(Span(match[1], start, end, 'identifier'))
    # A known space-containing path remains one literal, including unquoted
    # references. Its component filenames cannot become separate subjects.
    known = ledger.written | {s for r in ledger.readings + ledger.inputs for s in r['subjects']}
    known |= {s for r in ledger.executions for s in r['subjects']}
    # D5/D16: dotted identifier syntax does not itself locate a file.
    spans = [Span(s.text, s.start, s.end, 'identifier')
             if s.kind == 'path' and '/' not in s.text and '\\' not in s.text
             and ledger.subject(s.text, event) not in known else s for s in spans]
    for subject in known:
        if not subject.startswith('file:') or ' ' not in subject:
            continue
        for spelling in path_spellings(subject[5:], event.get('cwd') or '/'):
            for match in re.finditer(r'(?<![\w/\\.])' + re.escape(spelling) + r'(?![\w/\\.])', text):
                spans = [s for s in spans if not (match.start() <= s.start and s.end <= match.end())]
                spans.append(Span(spelling, *match.span(), 'path'))
    # D9: a returned record's path value can preserve spaces in later prose.
    for reading in ledger.readings:
        for returned in reading['texts']:
            for line in returned.splitlines():
                _, separator, value = line.partition(': ')
                if (separator and ' ' in value and reading['source']
                        and re.match(r'^(?:[A-Za-z]:[/\\]|[/\\]|\.{1,2}[/\\])', value)
                        and name_kind(value, quoted=True) == 'path'):
                    for match in re.finditer(re.escape(value), text):
                        spans = [s for s in spans if not (match.start() <= s.start and s.end <= match.end())]
                        spans.append(Span(value, *match.span(), 'path'))
    spans.sort(key=lambda s: (s.start, s.end))
    if event.get('tool_name') not in WRITERS:
        return text, spans
    # A syntactically complete program defines new names/values. References to
    # earlier recorded things and external locations still make claims in it.
    try:
        tree = ast.parse(text)
        program = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign, ast.Import, ast.ImportFrom, ast.Raise, ast.Assert, ast.If, ast.For, ast.While, ast.With, ast.Try))
                      or isinstance(n, ast.Expr) and isinstance(n.value, (ast.Dict, ast.List, ast.Tuple, ast.Call))
                      for n in tree.body)
    except SyntaxError:
        program = False
    if not program:
        return text, spans
    prior = ledger.given + ledger.own + [t for r in ledger.readings + ledger.inputs for t in r['texts']]
    # Comments and sentence-shaped strings assert facts even inside programs.
    assertions = []
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT or token.type == tokenize.STRING and re.search(r'\b(?:is|are|was|were|has|have|returns?|outputs?|produces?|accepts?|contains?|does|will)\b', token.string):
            assertions.append((offsets[token.start[0] - 1] + token.start[1], offsets[token.end[0] - 1] + token.end[1]))
    return text, [s for s in spans if any(start <= s.start and s.end <= end for start, end in assertions) or s.kind in ('path', 'url', 'external-package') or any(contains(t, s.text, s.kind) for t in prior)]
