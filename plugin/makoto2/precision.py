"""Exact form spans, independent of the hook and reusable by DetIO.

The closed common-word list is the documented deterministic catch-all rule.
No stemming, spelling correction, path normalization or semantic classification.
"""
from dataclasses import dataclass
from pathlib import Path
import re

COMMON = frozenset(Path(__file__).with_name('common-english.txt').read_text(encoding='utf-8').split())


@dataclass(frozen=True)
class Span:
    text: str
    start: int
    end: int
    kind: str


# Each delimited payload is one exact span, including its whitespace.
DELIMITED = re.compile(r'```[^\n]*\n(?P<fence>[\s\S]*?)```|~~~[^\n]*\n(?P<tilde>[\s\S]*?)~~~|`(?P<tick>[^`\n]+)`|"(?P<double>(?:\\.|[^"\\])*)"|(?<!\w)\x27(?P<single>(?:\\.|[^\x27\\])*)\x27(?!\w)|“(?P<curly>[^”]*)”|‘(?P<quote>[^’]*)’')
TOKEN = re.compile(r'[^\s<>"\x27`“”‘’]+(?:[\x27’][^\s<>"\x27`“”‘’]+)*', re.UNICODE)
URL = re.compile(r'https?://[^\s<>"\x27`“”‘’]+')
# Retain compact prerelease/postrelease/build spellings. Only terminal sentence
# punctuation is excluded; this is a lexical slice, not a version validator.
PACKAGE_VERSION = r'\d(?:[\w.+-]*\w)?'
VERSIONED = re.compile(r'(?<![\w/])(?P<package>@?[A-Za-z][\w.-]*(?:/[\w.-]+)?)\s*(?:@|==|>=|<=|~=|\bv(?:ersion)?\s*|\s+(?=\d+\.\d))\s*(?P<version>' + PACKAGE_VERSION + r')(?![\w+.-]*\w)')
UNIT = re.compile(r'(?<!\w)[+-]?\d+(?:\.\d+)?\s*(?:[A-Za-zµμ°%]+(?:/[A-Za-z]+)?)(?!\w)')
GRAMMAR_WORDS = frozenset('a an the is are was were be been being am has have had do does did of for to from in on at by with without as than and or but if then it its this that these those'.split())
VERSION_LABELS = frozenset('version revision release edition build'.split())
RESULT_VERBS = frozenset('outputs produces returns prints equals'.split())


def extract(text, *, tool_output=False):
    """Return all precision spans with original offsets; never regenerate bytes.

    tool_output=True preserves each complete nonempty output line in addition
    to lexical spans. Callers may pass prior output lines back via exact matching.
    """
    found = {}

    def add(start, end, kind):
        if end > start:
            found.setdefault((start, end), Span(text[start:end], start, end, kind))

    for match in DELIMITED.finditer(text):
        name = match.lastgroup
        add(*match.span(name), 'delimited')
    for match in URL.finditer(text):
        start, end = match.span()
        while end > start and text[end-1] in '.,;!?)]}':
            end -= 1
        add(start, end, 'url')
    for pattern, kind in ((VERSIONED, 'external-package'), (UNIT, 'unit')):
        for match in pattern.finditer(text):
            if kind == 'external-package':
                separator = text[match.end('package'):match.start('version')]
                if separator.isspace() and match['package'].lower() in GRAMMAR_WORDS:
                    continue
                if separator.isspace() and (match['package'].lower() in VERSION_LABELS
                        or match['package'].lower() in RESULT_VERBS and re.fullmatch(r'\d+\.\d+', match['version'])):
                    continue
                # A whitespace pair can accidentally attach the preceding
                # prose word to a measurement. Explicit package operators/v
                # forms are still names; a numeric slice of a unit is a value.
                if separator.isspace() and any(unit.start() <= match.start('version')
                        and match.end('version') <= unit.end()
                        and re.sub(r'^[+-]?\d+(?:\.\d+)?\s*', '', unit.group()).lower() not in GRAMMAR_WORDS
                        for unit in UNIT.finditer(text)):
                    continue
            add(*match.span(), kind)
    for match in TOKEN.finditer(text):
        start, end = match.span()
        value = match.group()
        if (start > 0 and text[start - 1] == '<' and end < len(text) and text[end] == '>'
                and re.fullmatch(r'/?[A-Za-z][\w:-]*', value)):
            continue  # Markup tags are syntax, not authored file paths.
        # Sentence punctuation is outside a token. Internal punctuation is exact.
        while value.endswith(('.', ',', ';', ':', '?', '!')):
            value = value[:-1]
            end -= 1
        if not value or not any(c.isalnum() for c in value):
            continue
        if value.startswith(('https://', 'http://')):
            kind = 'url'
        elif '@' in value and '.' in value.split('@')[-1]:
            kind = 'email'
        elif '/' in value or '\\' in value or re.search(r'\w\.\w', value):
            kind = 'path'
        elif any(c.isdigit() for c in value):
            kind = 'digit'
        elif any(not c.isalpha() for c in value) or re.search(r'[a-z][A-Z]', value):
            kind = 'identifier'
        elif value.lower() not in COMMON:
            kind = 'non-dictionary'
        else:
            continue
        add(start, end, kind)
    # Visible log/stack syntax is a form, irrespective of its subject.
    for match in re.finditer(r'(?m)^(?:\s*(?:Error|ERROR|Fatal|FATAL|Traceback|WARNING|WARN|INFO|DEBUG)(?::|\b)[^\n]*|\s+at [^\n]*|\s*File "[^\n]*|\[\d[^\n]*)$', text):
        add(*match.span(), 'output-line')
    if tool_output:
        offset = 0
        for line in text.splitlines(keepends=True):
            add(offset, offset + len(line.rstrip('\r\n')), 'output-line')
            offset += len(line)
    return sorted(found.values(), key=lambda s: (s.start, -s.end, s.kind))


UUID = re.compile(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')
HASH = re.compile(r'(?=[0-9a-fA-F]*[a-fA-F])(?=[0-9a-fA-F]*\d)[0-9a-fA-F]{7,64}|[a-fA-F]{32}|[a-fA-F]{40}|[a-fA-F]{64}')
VERSION = re.compile(r'(?:v\d+(?:\.\d+)+|\d+(?:\.\d+){2,})(?:-[A-Za-z0-9.-]+)?(?:\+[A-Za-z0-9.-]+)?')
EMAIL = re.compile(r'[A-Za-z0-9.!#$%&*+/=?^_{}|~+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+')
MODULE = re.compile(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+')
FILENAME = re.compile(r'(?:\.[A-Za-z_][\w.-]*|[\w-]+(?:\.[\w-]+)*\.[A-Za-z_][\w-]*)(?::\d+(?::\d+)?)?')
IDENTIFIER = re.compile(r'[A-Za-z_]\w*')
ALPHANUMERIC_ID = re.compile(r'(?=[A-Za-z0-9_-]*\d)[A-Za-z][A-Za-z0-9_-]*')
PATH = re.compile(r'(?:[A-Za-z]:[\\/]|[.~]?[\\/]|\.\.[\\/])?[^\s<>"\x27`|?*()\[\]{}]+(?:[\\/][^\s<>"\x27`|?*()\[\]{}]+)*[\\/]?')


def name_kind(value, *, quoted=False):
    """Closed lexical NAME forms, independent of the common-word allowlist.

    A dotted numeric pair is a decimal; versions have three numeric components
    or an explicit v prefix. Short hex hashes require letters and digits; long
    all-letter hashes use fixed 32/40/64 widths. All digits remain numbers.
    Hyphenated alphabetic words and digit-leading unit values are not identifiers.
    """
    if re.fullmatch(r'https?://[^\s<>"\x27`“”‘’]+', value):
        return 'url'
    if EMAIL.fullmatch(value):
        return 'email'
    if (UUID.fullmatch(value) or HASH.fullmatch(value) or VERSION.fullmatch(value)
            or re.fullmatch(r'[A-Za-z][\w-]*-\d+(?:\.\d+)+(?:[-+][\w.-]+)?', value)):
        return 'identifier'
    if VERSIONED.fullmatch(value):
        return 'external-package'
    if MODULE.fullmatch(value) or FILENAME.fullmatch(value):
        return 'path'  # Files and dotted modules share exact boundary matching.
    if PATH.fullmatch(value) and ('/' in value or '\\' in value):
        # A ratio of plain numbers is a value, not a file name.
        if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?/\d+(?:\.\d+)?', value):
            return 'path'
    if quoted and ' ' in value and '\n' not in value and '\r' not in value:
        if re.search(r'\s[/\\]\s', value):
            return None
        lexical = value.replace(' ', '_')
        if FILENAME.fullmatch(lexical) or PATH.fullmatch(lexical) and ('/' in lexical or '\\' in lexical):
            return 'path'
    if IDENTIFIER.fullmatch(value) and ('_' in value or re.search(r'[a-z][A-Z]', value)):
        return 'identifier'
    if ALPHANUMERIC_ID.fullmatch(value):
        return 'identifier'
    return None


def names(text, *, shell=False):
    """NAME-only view of extract(), retaining original bytes and offsets.

    Quoting never promotes prose or values to names. Whole output lines and
    unit spans stay in the general extractor, while names inside them still count.
    Surrounding token brackets are punctuation, not part of a name.
    """
    found = {}
    spans = extract(text)
    units = [s for s in spans if s.kind == 'unit']
    # Shell quotes around commit messages delimit prose argv, not one filename.
    messages = {(s.start, s.end) for s in spans if shell and s.kind == 'delimited'
                and re.search(r'(?:-[A-Za-z]*m|--message)(?:\s+|=)[\x27"]$', text[:s.start])}
    delimited_names = [s for s in spans if s.kind == 'delimited' and name_kind(s.text, quoted=True)
                       and not re.match(r'^[A-Za-z_]\w*=', s.text) and (s.start, s.end) not in messages]
    for span in spans:
        if any(s.start <= span.start and span.end <= s.end and (span.start, span.end) != (s.start, s.end) for s in delimited_names):
            continue
        if span.kind == 'output-line' or span.kind == 'unit' and not HASH.fullmatch(span.text):
            continue
        if (span.start, span.end) in messages:
            continue
        # Split token wrappers too: Markdown [label](path) and call(id_name)
        # still name the enclosed path/identifier. A complete URL wins first.
        candidates = [(span.start, span.end)]
        assignment = re.match(r'^[A-Za-z_]\w*=', span.text)
        if assignment:
            candidates = [(span.start, span.start + assignment.end() - 1),
                          (span.start + assignment.end(), span.end)]
        elif not name_kind(span.text, quoted=span.kind == 'delimited'):
            candidates += [(span.start + m.start(), span.start + m.end())
                           for m in re.finditer(r'[^\s()\[\]{}]+', span.text)]
        for start, end in candidates:
            value = text[start:end]
            if any(u.start <= start and end <= u.end for u in units) and not (HASH.fullmatch(value) or UUID.fullmatch(value) or VERSION.fullmatch(value)):
                continue
            kind = name_kind(value, quoted=span.kind == 'delimited' and (start, end) == (span.start, span.end))
            if kind:
                found.setdefault((start, end), Span(value, start, end, kind))
    return sorted(found.values(), key=lambda s: (s.start, -s.end, s.kind))


def package_parts(value):
    """Exact package/version components, independent of separator spelling."""
    match = VERSIONED.fullmatch(value)
    return (match['package'], match['version']) if match else None


def contains(text, span, kind=None):
    """Exact characters with token boundaries; 731 is not evidence for 73."""
    strict = kind in ('path', 'email', 'url', 'identifier', 'digit', 'external-package')
    def edge(char):
        punctuation = '/\\.@+~%#?&$!*|-'
        if kind in ('path', 'url', 'external-package'):
            punctuation += ':'
        if kind == 'url':
            punctuation += '='
        return char.isalnum() or char == '_' or strict and char in punctuation
    start = 0
    while (at := text.find(span, start)) >= 0:
        end = at + len(span)
        if (not edge(span[0]) or at == 0 or not edge(text[at-1])) and (not edge(span[-1]) or end == len(text) or not edge(text[end])):
            return True
        start = at + 1
    return False
