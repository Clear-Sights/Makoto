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
URL = re.compile(r'https?://[^\s<>"\x27`]+')
VERSIONED = re.compile(r'(?<![\w/])(?:@?[A-Za-z][\w.-]*(?:/[\w.-]+)?)\s*(?:@|==|>=|<=|~=|\bv(?:ersion)?\s*|\s+(?=\d+\.\d))\s*\d[\w.+-]*')
UNIT = re.compile(r'(?<!\w)[+-]?\d+(?:\.\d+)?\s*(?:[A-Za-zµμ°%]+(?:/[A-Za-z]+)?)(?!\w)')


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
            add(*match.span(), kind)
    for match in TOKEN.finditer(text):
        start, end = match.span()
        value = match.group()
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


def contains(text, span, kind=None):
    """Exact characters with token boundaries; 731 is not evidence for 73."""
    strict = kind in ('path', 'email', 'url', 'identifier', 'digit', 'external-package')
    def edge(char):
        return char.isalnum() or char == '_' or strict and char in '/\\.@:+~%#?=&$!*|-'
    start = 0
    while (at := text.find(span, start)) >= 0:
        end = at + len(span)
        if (not edge(span[0]) or at == 0 or not edge(text[at-1])) and (not edge(span[-1]) or end == len(text) or not edge(text[end])):
            return True
        start = at + 1
    return False
