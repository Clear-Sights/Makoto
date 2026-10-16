"""Makoto: the four-question hook. Live entry: cd plugin && python3 -m makoto2,
one serialized native Claude Code hook event on stdin, one JSON response on stdout.

Sections, in dependency order: paths, shell, borrowed, precision, observed, transcript, switch, shipping, creations, provenance, evaluate, hook, __main__.
Modified excerpts from DetIO and Causality (leaves, get, receipt) are credited in NOTICE.
"""
import ast
import contextlib
import fnmatch
import hashlib
import json
import marshal
import ntpath
import os
import posixpath
import re
import shlex
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Defaults; MAKOTO_STATE_DIR, MAKOTO_ADAPTER, MAKOTO_LOCK_SECONDS, MAKOTO_CHECKPOINT and MAKOTO_BLOCK_IN override (see README).
CONFIG = {'state_dir': '~/.claude/makoto2_state', 'adapter': 'inferred', 'lock_seconds': 3.0}


# ======================================================================
# paths: Recorded file paths are portable identities, independent of the hook host.

def flavour(*paths):
    return ntpath if any(ntpath.splitdrive(path)[0] for path in paths) else posixpath


def normalized_path(path, cwd):
    """Bind relative paths and retain drives/UNC roots, using '/' in keys."""
    path, cwd = path.replace('\\', '/'), cwd.replace('\\', '/')
    paths = flavour(path, cwd)
    return paths.normpath(paths.join(cwd, path)).replace('\\', '/')


def relative_path(path, cwd):
    """A different drive/share has no relative spelling; never call relpath."""
    path, cwd = path.replace('\\', '/'), cwd.replace('\\', '/')
    paths = flavour(path, cwd)
    if paths is ntpath and ntpath.splitdrive(path)[0].lower() != ntpath.splitdrive(cwd)[0].lower():
        return None
    return paths.relpath(path, cwd).replace('\\', '/')


def path_spellings(path, cwd):
    """Equivalent separator spellings for output paths and change references."""
    spellings = {path}
    relative = relative_path(path, cwd)
    if relative is not None:
        spellings.update((relative, './' + relative))
    return spellings | {value.replace('/', '\\') for value in spellings}


def program_name(path):
    """Bash may invoke a Windows executable with either separator."""
    name = ntpath.basename(path)
    return name[:-4] if name.lower().endswith('.exe') else name


# ======================================================================
# shell: Conservative lexical command order; never evaluates shell text.

@lru_cache(maxsize=512)
def redirected_argv(command):
    """Separate unquoted static redirects from a single command's argv."""
    parts = ordered_segments(command)
    if parts is None or len(parts) != 1:
        return None
    try:
        lex = shlex.shlex(parts[0][0], posix=False, punctuation_chars='<>')
        lex.whitespace_split = True
        raw = list(lex)
        words, redirects = [], []
        i = 0
        while i < len(raw):
            word = raw[i]
            if word in ('<', '>', '>>', '>|', '<<', '<<-'):
                if i + 1 >= len(raw):
                    return None
                target = shlex.split(raw[i + 1])[0]
                if words and words[-1].isdigit():
                    words.pop()  # descriptor prefix, e.g. 2>errors.txt
                redirects.append((word, target))
                i += 2
                continue
            decoded = shlex.split(word)
            if len(decoded) != 1:
                return None
            words.append(decoded[0])
            i += 1
        return tuple(words), tuple(redirects)
    except (ValueError, IndexError):
        return None


@lru_cache(maxsize=512)
def ordered_segments(command):
    """Return (command, preceding separator) pairs, or None for opaque syntax.

    Quotes, escapes, comments and nested substitutions protect separators.
    Heredoc bodies are consumed as data, not commands. Shell compound control
    flow, subshells and background jobs deliberately retain the legacy adapter.
    """
    parts, current, docs = [], [], []
    link, quote, stack = None, None, []
    i = 0

    def flush(separator):
        nonlocal current, link
        text = ''.join(current).strip()
        if text:
            parts.append((text, link))
        current, link = [], separator

    while i < len(command):
        c = command[i]
        if c == '\\' and quote != "'":
            if i + 1 == len(command):
                return None
            current.append(command[i:i + 2] if command[i + 1] != '\n' else '')
            i += 2
            continue
        if quote:
            current.append(c)
            if c == quote:
                quote = None
            elif c == '$' and quote == '"' and command[i:i + 2] == '$(':
                # Substitution quotes are independent of the enclosing quote.
                stack.append((')', quote))
                quote = None
                current.append('(')
                i += 1
            i += 1
            continue
        if c in "'\"`":
            quote = c
            current.append(c)
        elif command[i:i + 2] in ('$(', '${'):
            stack.append((')' if command[i + 1] == '(' else '}', None))
            current.append(command[i:i + 2])
            i += 1
        elif stack:
            current.append(c)
            if c == '(' and stack[-1][0] == ')':
                stack.append((')', None))
            elif c == stack[-1][0]:
                _, quote = stack.pop()
        elif c == '#' and (not current or current[-1][-1:].isspace()):
            end = command.find('\n', i)
            i = len(command) if end < 0 else end
            continue
        elif command[i:i + 2] == '<<':
            match = re.match(r'<<(-?)\s*(\x27[^\x27\n]+\x27|"[^"\n]+"|[\w.-]+)', command[i:])
            if not match:
                return None
            docs.append((shlex.split(match[2])[0], bool(match[1])))
            current.append(match[0])
            i += len(match[0]) - 1
        elif c in '(){}' or c == '&' and command[i:i + 2] != '&&':
            # & in a redirect is not a background operator.
            if c == '&' and current and current[-1].endswith(('>', '<')):
                current.append(c)
            else:
                return None
        elif c in ';|&\n':
            separator = c
            if command[i:i + 2] in ('&&', '||'):
                separator = command[i:i + 2]
                i += 1
            if command[i:i + 2] in (';;', '|&'):
                return None
            flush(separator)
            if c == '\n' and docs:
                i += 1
                for delimiter, tabs in docs:
                    while i < len(command):
                        end = command.find('\n', i)
                        end = len(command) if end < 0 else end
                        line = command[i:end]
                        i = end + (end < len(command))
                        if (line.lstrip('\t') if tabs else line) == delimiter:
                            break
                    else:
                        return None
                    if (line.lstrip('\t') if tabs else line) != delimiter:
                        return None
                docs = []
                continue
        else:
            current.append(c)
        i += 1
    if quote or stack or docs:
        return None
    flush(None)
    for text, _ in parts:
        try:
            first = shlex.split(text)[0]
        except (ValueError, IndexError):
            return None
        if first in ('if', 'then', 'else', 'elif', 'fi', 'for', 'while', 'until', 'do', 'done', 'case', 'esac', 'function', 'select', '!', 'coproc'):
            return None
    return tuple(parts)


def selected_segments(command, post):
    """Resolve literal short circuits; uncertain branch selection stays opaque."""
    parts = ordered_segments(command)
    if parts is None:
        return None
    response = post.get('tool_response')
    success = post.get('hook_event_name') != 'PostToolUseFailure' and not (
        isinstance(response, dict) and (response.get('is_error') or response.get('isError')
        or next((response[k] for k in ('exitCode', 'exit_code', 'exit') if k in response), 0)))
    selected, status = [], None
    for text, link in parts:
        if link == '&&' and status is False or link == '||' and status is True:
            continue
        if link == '||' and status is None or link == '&&' and status is None and not success:
            return None
        selected.append(text)
        words = shlex.split(text)
        status = True if words == ['true'] or words == [':'] else False if words == ['false'] else None
    return selected


# ======================================================================
# borrowed: Modified excerpts from DetIO and Causality; source pins in NOTICE.
#
# Copyright 2026 Clear-Sights. Licensed under Apache-2.0 (LICENSE).
# Changes: numeric leaves, explicit store, SHA verification, call-site traces.

def leaves(r, path=()):
    """DetIO core.leaves: every string in a nested native response."""
    if isinstance(r, str):
        yield path, r
    elif type(r) in (int, float):
        yield path, str(r)
    for k, v in (r.items() if isinstance(r, dict) else enumerate(r) if isinstance(r, list) else ()):
        yield from leaves(v, path + (k,))


def get(store, address):
    """Adapted DetIO core.get: only a witnessed content address is opened."""
    if not re.fullmatch(r'[0-9a-f]{12}|[0-9a-f]{64}', address):
        raise ValueError('invalid DetIO address')
    data = (Path(store).expanduser() / 'objects' / address).read_bytes()
    if not hashlib.sha256(data).hexdigest().startswith(address):
        raise ValueError('DetIO object does not match its bytes')
    return data.decode('utf-8')


def receipt(claim, trace, fingerprint):
    # Causality receipt, copied unchanged; no trace-free admitted write.
    if not trace:
        raise ValueError("a claim without a trace is a belief, not a receipt")
    return {"claim": claim, "trace": trace, "instruments": fingerprint}


def fragments(value):
    """Tool input/response includes its literal field names as well as values."""
    for _, v in leaves(value):
        yield v
        # A connector returns its JSON as one string; what the session saw is
        # the decoded text, so tabs and quotes inside bodies match their source.
        if isinstance(v, str) and v[:1] in '{[' and '\\' in v:
            try:
                decoded = json.loads(v)
            except ValueError:
                continue
            if isinstance(decoded, (dict, list)):
                yield from fragments(decoded)
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            if isinstance(child, (dict, list)):
                yield from fragments(child)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                yield from fragments(child)


# ======================================================================
# precision: Exact form spans, independent of the hook and reusable by DetIO.
#
# The closed common-word list is the documented deterministic catch-all rule.
# No stemming, spelling correction, path normalization or semantic classification.

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
                if (separator.isspace() or separator.strip().lower() in VERSION_LABELS) and match['package'].lower() in GRAMMAR_WORDS:
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


# ======================================================================
# observed: Lexical native tool adapters; no subject-specific vocabulary or execution.

WRITERS = {'Write', 'Edit', 'MultiEdit', 'NotebookEdit'}
FINAL = {'Stop', 'SubagentStop', 'PreDelivery'}


def digest(value):
    return hashlib.sha256((value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()


def identity(value, event):
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(',', ':'))
    if not isinstance(value, str) or not value:
        raise ValueError('subject identity must be nonempty')
    if value.startswith(('https://', 'http://', 'id:', 'command:')):
        return value
    return 'file:' + normalized_path(value.removeprefix('file:'), event.get('cwd') or os.getcwd())


def shell_segments(command):
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=';&|()<>\n')
        lex.whitespace = ' \t\r'
        lex.whitespace_split = True
        segments, current = [], []
        for word in lex:
            if word and all(c in ';&|()<>\n' for c in word):
                if current:
                    segments.append(current)
                current = [word] if '<' in word or '>' in word else []
            else:
                current.append(word)
        if current:
            segments.append(current)
        return segments
    except ValueError:
        return []


def programs(event):
    command = event.get('tool_input', {}).get('command', '')
    ordered = ordered_segments(command)
    segments = [(redirected_argv(text) or (shlex.split(text), []))[0]
                for text, _ in ordered] if ordered is not None else shell_segments(command)
    for words in segments:
        while words and (re.match(r'^[A-Za-z_]\w*=', words[0]) or words[0] in ('env', 'command', 'exec', 'sudo')):
            words = words[1:]
        if words and words[0]:
            yield words


def git_action(event):
    for words in programs(event):
        if program_name(words[0]) != 'git':
            continue
        i = 1
        while i < len(words) and words[i].startswith('-'):
            i += 2 if words[i] in ('-C', '-c', '--git-dir', '--work-tree') else 1
        if i < len(words) and words[i] in ('commit', 'push'):
            return True
    return False


def dependent(event):
    return event['hook_event_name'] in FINAL or event['hook_event_name'] == 'PreToolUse' and (event.get('tool_name') in WRITERS or event.get('tool_name') == 'Bash' and git_action(event))


def text_of(event):
    if event['hook_event_name'] in FINAL:
        return event.get('last_assistant_message', '')
    ti = event.get('tool_input', {})
    # Inputs' keys are protocol, not authored content. Include writer targets.
    return '\n'.join(value for _, value in leaves(ti))


def response_text(response):
    return '\n'.join(value for _, value in leaves(response))


def failed(event):
    response = event.get('tool_response', {})
    return event['hook_event_name'] == 'PostToolUseFailure' or isinstance(response, dict) and bool(response.get('is_error') or response.get('isError') or next((response[k] for k in ('exitCode', 'exit_code', 'exit') if k in response), 0))


# A hook's own refusal of a file write, as the host echoes it back: Makoto's
# reasons (hook.d_out) and the host's "PreToolUse:Edit hook error" wording.
REFUSAL = re.compile(r'^\s*(?:PreToolUse(?::[\w*]+)?\s+hook\s+(?:error|denied|blocked)\b|hook\s+(?:denied|blocked)\b|makoto (?:rule [a-d]|contract|transport)\b)', re.I)


def refused(event):
    """A file write the host reports as refused by a hook never ran.

    Only an error result of a writer that opens with a refusal counts. Any other
    failure may have partly written, so it keeps counting as a change.
    """
    return (event.get('tool_name') in WRITERS and failed(event)
            and bool(REFUSAL.match(response_text(event.get('tool_response')))))


def effects(event):
    result = []
    ti, tool = event.get('tool_input', {}), event.get('tool_name')
    if tool in WRITERS:
        target = ti.get('file_path') or ti.get('notebook_path')
        if target:
            result.append({'subject': target})
    if tool == 'Bash':
        ordered = ordered_segments(ti.get('command', ''))
        if ordered is not None:
            for command, _ in ordered:
                parsed = redirected_argv(command)
                if parsed:
                    result.extend({'subject': target} for operator, target in parsed[1]
                                  if operator in ('>', '>>', '>|') and not target.startswith('&')
                                  and not any(c in target for c in '$*?`'))
        else:
            # Opaque calls retain the legacy conservative mutation adapter.
            for words in shell_segments(ti.get('command', '')):
                if words and words[0] in ('>', '>>', '>|') and len(words) > 1:
                    result.append({'subject': words[1]})
        for words in programs(event):
            name = program_name(words[0])
            if '>' in words[0] and len(words) > 1:
                result.append({'subject': words[1]})
            elif name in ('rm', 'rmdir'):
                # A deleted file or tree is no longer an edit anyone can run.
                result.extend({'subject': w, 'removed': True} for w in words[1:] if w and not w.startswith('-'))
            elif name in ('touch', 'mkdir', 'truncate', 'tee'):
                result.extend({'subject': w} for w in words[1:] if w and not w.startswith('-'))
            elif name in ('cp', 'mv') and len(words) > 2:
                result.append(dict(subject=words[-1], **({'renamed_from': words[-2]} if name == 'mv' else {})))
                if name == 'mv':
                    result.append({'subject': words[-2], 'removed': True})
            elif name == 'sed' and any(w.startswith('-i') for w in words[1:]):
                result.append({'subject': words[-1]})
            elif name == 'gofmt' and '-w' in words[1:]:
                result.extend({'subject': w} for w in words[1:] if w != '-w' and not w.startswith('-'))
    return list(event.get('makoto', {}).get('effects', [])) + [r for r in result if r['subject'] != '' and not any(c in r['subject'] for c in '$*?`')]


def reading_subjects(pre):
    ti, name = pre.get('tool_input', {}), pre.get('tool_name')
    result = [r['subject'] for r in pre.get('makoto', {}).get('reads', [])]
    if name in ('Read', 'NotebookRead'):
        if target := ti.get('file_path') or ti.get('notebook_path'):
            result.append(target)
    elif name in ('Grep', 'Glob'):
        result.append(ti.get('path') or pre.get('cwd') or '.')
    elif name == 'WebFetch' and ti.get('url'):
        result.append(ti['url'])
    elif name == 'Bash':
        for words in programs(pre):
            if program_name(words[0]) in ('cat', 'head', 'tail', 'less', 'more', 'wc', 'rg', 'grep', 'ls', 'stat', 'find'):
                result.extend(w for w in words[1:] if w and not w.startswith('-'))
            # Executing a program reads its response, not the program file.
            # Only direct file readers above inherit that file's own/stale status.
    return result


def network_targets(pre, post):
    ti, name = pre.get('tool_input', {}), pre.get('tool_name')
    result = []
    if name == 'WebFetch' and ti.get('url'):
        result.append(ti['url'])
    elif name == 'WebSearch':
        # A search pays subjects in its query and returned source links.
        result.extend(v for _, v in leaves(ti))
        result.extend(v for _, v in leaves(post.get('tool_response')))
    elif name == 'Bash':
        for words in programs(pre):
            if any(w in ('--offline', '--no-index') for w in words):
                continue
            if program_name(words[0]) in ('curl', 'wget', 'http', 'https', 'fetch'):
                result.extend(w for w in words[1:] if w and not w.startswith('-'))
            elif (program_name(words[0]) in ('pip', 'pip3', 'npm', 'pnpm', 'yarn', 'cargo', 'go') and any(w in ('install', 'add', 'get', 'view') for w in words[1:])) or program_name(words[0]) == 'git' and any(w in ('fetch', 'clone', 'pull') for w in words[1:]):
                result.extend(w for w in words[1:] if w)
    result.extend(pre.get('makoto', {}).get('network_subjects', []))
    return result


# ======================================================================
# transcript: Read host transcript history without promoting assistant text to evidence.
#
# Native JSONL hook rows and Claude message/tool_use/tool_result rows are accepted.
# The current candidate is excluded. Journal decisions override matching imports.

def key(event):
    name = event['hook_event_name']
    if name in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure'):
        return (name.replace('PostToolUseFailure', 'PostToolUse'), event.get('tool_use_id'))
    if name == 'UserPromptSubmit':
        return (name, digest(event.get('prompt', '')))
    return (name, digest(event))


def transcript_cache(path, session_id):
    """Parse state of one transcript: events parsed so far (uncut; rows without their own cwd
    take the candidate's at use), the tool calls still awaiting a result, and the byte offset
    after the last complete line. A line that cannot be parsed stops the parse where it is."""
    return {'path': path, 'session_id': session_id, 'offset': 0, 'events': [], 'nocwd': [],
            'first_pre': {}, 'pending': {}, 'error': None}


def parse_transcript(cache):
    """Read only the bytes after cache['offset'], complete lines only, and extend the cache."""
    with Path(cache['path']).open('rb') as stream:
        size = stream.seek(0, 2)
        if size < cache['offset']:
            # Truncated or replaced: what was parsed is no longer the file.
            cache.update(transcript_cache(cache['path'], cache['session_id']))
        if cache['error'] is not None:
            return cache
        stream.seek(cache['offset'])
        data = stream.read(size - cache['offset'])
    data = data[:data.rfind(b'\n') + 1]
    events, nocwd, pending = cache['events'], cache['nocwd'], cache['pending']
    def add(event, own_cwd):
        if event.get('hook_event_name') == 'PreToolUse':
            cache['first_pre'].setdefault(event.get('tool_use_id'), len(events))
        events.append(event)
        nocwd.append(not own_cwd)
    for line in data.splitlines(keepends=True):
        try:
            row = json.loads(line.decode('utf-8'))
            if row.get('session_id', row.get('sessionId', cache['session_id'])) != cache['session_id']:
                raise ValueError('transcript session identity mismatch')
            base = {'session_id': cache['session_id']}
            own_cwd = 'cwd' in row
            if own_cwd:
                base['cwd'] = row['cwd']
            if row.get('hook_event_name'):
                add(dict(base, **row), own_cwd)
            else:
                message = row.get('message', {})
                role = message.get('role', row.get('type'))
                content = message.get('content', [])
                if role == 'user' and isinstance(content, str):
                    add(dict(base, hook_event_name='UserPromptSubmit', prompt=content), own_cwd)
                elif isinstance(content, list):
                    prompts = []
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if role == 'assistant' and block.get('type') == 'tool_use':
                            event = dict(base, hook_event_name='PreToolUse', tool_name=block['name'], tool_use_id=block['id'], tool_input=block.get('input', {}))
                            add(event, own_cwd)
                            pending[block['id']] = {'tool_name': event['tool_name'], 'tool_input': event['tool_input']}
                        elif role == 'user' and block.get('type') == 'tool_result':
                            tid = block['tool_use_id']
                            pre = pending.get(tid, {})
                            response = block.get('content', '')
                            if pre.get('tool_name') == 'Bash' and isinstance(response, str):
                                # No inferred exit status: host block status is authoritative.
                                response = {'stdout': response, 'is_error': block.get('is_error', False)}
                            elif block.get('is_error'):
                                response = {'content': response, 'is_error': True}
                            add(dict(base, hook_event_name='PostToolUse', tool_name=pre.get('tool_name'), tool_use_id=tid, tool_input=pre.get('tool_input', {}), tool_response=response), own_cwd)
                        elif role == 'user' and block.get('type') == 'text':
                            prompts.append(block.get('text', ''))
                    if prompts:
                        prompt = dict(base, hook_event_name='UserPromptSubmit', prompt='\n'.join(prompts))
                        if any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in content):
                            # Text riding on a tool result is harness reminder text for
                            # the same turn; it is given prose but never a new turn.
                            prompt['makoto'] = {'same_turn': True}
                        add(prompt, own_cwd)
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
            cache['error'] = [len(events), str(error)]
            return cache
        cache['offset'] += len(line)
    return cache


def history(candidate, journal, cache=None):
    """Records before the candidate: (event, admitted, tag), the tag naming where each came from."""
    path = candidate.get('transcript_path')
    if not path:
        return [(row['event'], row['admitted'], ('j', i)) for i, row in enumerate(journal)], None
    if cache is None or cache.get('path') != path:
        cache = transcript_cache(path, candidate['session_id'])
    try:
        parse_transcript(cache)
    except FileNotFoundError:
        # The host can submit a prompt before writing its first transcript.
        # Missing history adds no evidence and never replaces the verified journal.
        return merge([], journal), None
    # The candidate's own call and everything after it are excluded.
    current = candidate.get('tool_use_id')
    if cache['error'] is not None and current not in cache['first_pre']:
        # The parse stopped on a bad line before reaching the candidate.
        raise ValueError(cache['error'][1])
    cut = cache['first_pre'].get(current, len(cache['events']))
    cwd = candidate.get('cwd', '')
    imported = [dict(event, cwd=cwd) if bare else event for event, bare in zip(cache['events'][:cut], cache['nocwd'][:cut])]
    return merge(imported, journal), cache


def merge(imported, journal):
    """Anchor imported history to journal order, preserving denied decisions."""
    rows = [(r['event'], r['admitted'], ('j', i)) for i, r in enumerate(journal)]
    def occurrence_keys(events):
        counts = {}
        for event in events:
            k = key(event)
            counts[k] = counts.get(k, 0) + 1
            yield (k, counts[k])
    positions = {k: i for i, k in enumerate(occurrence_keys(e for e, _, _ in rows))}
    result, cursor, used = [], 0, set()
    for event, k in zip(imported, occurrence_keys(imported)):
        if k in positions:
            at = positions[k]
            if at >= cursor:
                result.extend(rows[cursor:at+1])
                cursor = at + 1
            used.add(k)
        elif k not in used:
            result.append((event, True, ('i',) + k))
            used.add(k)
    result.extend(rows[cursor:])
    return result


# ======================================================================
# switch: Rule d's lexical subjects and paired execution witnesses; never runs code.
#
# File suffixes, shebangs, notebook protocol and declaration syntax classify edits.
# Invocation positions classify executions, never words about claimed behavior.
# Opaque/conditional calls need the host's actual makoto.invocation subject.

CODE_SUFFIXES = frozenset('py pyw js jsx mjs cjs ts tsx sh bash zsh fish rb pl php lua r rs go c h cc cpp hpp java kt swift scala cs fs ex exs erl clj sql ps1 bat cmd ipynb tcl awk'.split())
CONFIG_SUFFIXES = frozenset('json jsonc yaml yml toml ini cfg conf config xml properties env'.split())
RECORD_SUFFIXES = frozenset('md txt rst csv tsv jsonl ndjson log'.split())
DATA_SUFFIXES = CONFIG_SUFFIXES | RECORD_SUFFIXES
CONFIG_FILES = frozenset(('Makefile', 'Dockerfile', 'Rakefile', 'Gemfile', 'Procfile', '.env'))
RUNTIMES = re.compile(r'(?:python(?:\d+(?:\.\d+)*)?|pypy\d*|node|nodejs|deno|bun|bash|sh|zsh|fish|ruby|perl|php|lua|Rscript|pwsh|tclsh(?:\d+(?:\.\d+)*)?|wish)\Z')
DECLARATIONS = re.compile(r'(?m)(?:\b(?:def|class|function|fn|func)\s+([A-Za-z_]\w*)|^\s*(?:export\s+)?(?:const\s+|let\s+|var\s+)?([A-Za-z_]\w*)\s*(?:=|:))')


def edited_forms(event, target):
    """Return code/data name forms for a recorded effect, or None."""
    path = target.removeprefix('file:')
    suffix = ntpath.splitext(path)[1].lstrip('.').lower()
    content = '\n'.join(value for _, value in leaves(event.get('tool_input', {})))
    payloads = [value for key, value in leaves(event.get('tool_input', {}))
                if key and key[-1] in ('content', 'new_string', 'old_string', 'new_source')]
    structured = False
    for value in payloads:
        try:
            structured |= isinstance(json.loads(value), (dict, list))
        except (ValueError, TypeError):
            pass
    shebang = bool(re.search(r'(?m)^#!\s*\S+', content))
    absolute = identity(target, event)[5:]
    executable = not suffix and os.path.isfile(absolute) and os.access(absolute, os.X_OK)
    record = (suffix in RECORD_SUFFIXES or not suffix and ntpath.basename(path) not in CONFIG_FILES and not executable) and event.get('tool_name') != 'NotebookEdit'
    data_form = (suffix in DATA_SUFFIXES or ntpath.basename(path) == '.env' or record) and event.get('tool_name') != 'NotebookEdit'
    data = data_form and not shebang
    if not (record or executable or suffix in CODE_SUFFIXES | DATA_SUFFIXES
            or ntpath.basename(path) in CONFIG_FILES
            or event.get('tool_name') == 'NotebookEdit'
            or re.search(r'(?m)^#!\s*\S+', content)
            or suffix not in ('md', 'rst', 'adoc') and (DECLARATIONS.search(content) or structured)):
        return None
    aliases = {s.text for s in names(content) if s.kind == 'identifier'}
    aliases.update(value for match in DECLARATIONS.finditer(content) for value in match.groups() if value)
    # JSON/YAML keys and dotted module names are also syntactic identifiers.
    aliases.update(re.findall(r'(?:^|[\n{,])\s*["\x27]([A-Za-z_]\w*)["\x27]\s*:', content))
    stem = ntpath.splitext(ntpath.basename(path))[0]
    if re.fullmatch(r'[A-Za-z_]\w*', stem):
        aliases.add(stem)
    relative = relative_path(absolute, event.get('cwd') or os.getcwd())
    module = ntpath.splitext(relative)[0].replace('/', '.') if relative is not None else ''
    if re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', module):
        aliases.add(module.removesuffix('.__init__'))
    return {'subject': identity(target, event), 'display': target, 'aliases': aliases,
            'data': data, 'data_form': data_form, 'record': record}


def full_read_subjects(pre, post):
    """Only completed full-file reads, never a search, slice or status receipt."""
    response = post.get('tool_response')
    if failed(post) or response is None:
        return set()
    if isinstance(response, dict):
        if any(response.get(key) for key in ('backgroundTaskId', 'session_id', 'sessionId', 'running', 'truncated', 'is_truncated')):
            return set()
        if not any(isinstance(response.get(key), str) for key in ('content', 'stdout', 'output')):
            return set()
    elif not isinstance(response, str):
        return set()
    ti, tool = pre.get('tool_input', {}), pre.get('tool_name')
    targets = []
    if tool == 'Read' and not any(key in ti for key in ('offset', 'limit', 'start_line', 'end_line', 'pages')):
        if ti.get('file_path'):
            targets.append(ti['file_path'])
    elif tool == 'Bash':
        words = simple_argv(ti.get('command', ''))
        if words and program_name(words[0]) == 'cat':
            args = words[1:]
            if args and args[0] == '--':
                args = args[1:]
            # One operand keeps returned bytes attributable to that same file.
            if len(args) == 1 and args[0] and args[0] != '-' and not args[0].startswith('-'):
                targets.extend(args)
    if tool == 'Bash':
        targets.extend(json_loaded_paths(ti.get('command', '')))
    for event in (pre, post):
        targets.extend(spec['subject'] for spec in event.get('makoto', {}).get('reads', [])
                       if spec.get('complete') is True and not spec.get('producer') and spec.get('role') != 'relay')
    return {identity(target, pre) for target in targets}


JSON_LOAD = re.compile(
    r"""json\.load\(\s*open\(\s*(['"])([^'"$*?`]+)\1\s*\)\s*\)"""
    r"""|json\.loads\(\s*open\(\s*(['"])([^'"$*?`]+)\3\s*\)\.read\(\s*\)\s*\)""")


def json_loaded_paths(command):
    """Files a successful `python -c` parsed whole with json.load on a literal path.

    json.load either consumes the entire file or raises, so a call that exits
    zero read the file in full. Statements joined by `;` hide an earlier
    failure behind a later exit status, so only a lone call or an `&&` chain
    counts.
    """
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=';&|()<>\n')
        lex.whitespace_split = True
        words = list(lex)
    except ValueError:
        return []
    statements, current = [], []
    for word in words:
        if word == '&&':
            statements.append(current)
            current = []
        elif word and all(c in ';&|()<>\n' for c in word):
            return []
        else:
            current.append(word)
    statements.append(current)
    paths = []
    for argv in statements:
        if len(argv) == 3 and re.fullmatch(r'python3?(?:\.\d+)?', program_name(argv[0])) and argv[1] == '-c':
            for match in JSON_LOAD.finditer(argv[2]):
                paths.append(match.group(2) or match.group(4))
    return paths


def names_change(event, change):
    """Every ship after code edits counts; writers require a literal name.

    A final answers for what its own agent wrote: a subagent's Stop is not held
    for a sibling worker's file. Commit and push still ship every agent's edits.
    """
    if event.get('tool_name') == 'Bash' and git_action(event):
        return True
    if event['hook_event_name'] in FINAL:
        return change.get('agent') == event.get('agent_id')
    text = text_of(event)
    # A worker that merely mentions a sibling worker's file is not answering for
    # it: the journal is shared by session, so each worker would otherwise
    # inherit every other worker's unrun items. Writing that file still counts.
    sibling = bool(event.get('agent_id')) and change.get('agent') not in (None, event['agent_id'])
    for span in ([] if sibling else names(text)):
        path = re.sub(r':\d+(?::\d+)?$', '', span.text)
        if span.kind == 'path' and identity(path, event) == change['subject']:
            return True
    # Include space-containing paths in writer targets and quoted prose.
    ti = event.get('tool_input', {})
    if any(identity(ti[key], event) == change['subject'] for key in ('file_path', 'notebook_path') if ti.get(key)):
        return True
    absolute = change['subject'][5:]
    if not sibling and any(contains(text, value, 'path') for value in path_spellings(absolute, event.get('cwd') or os.getcwd())):
        return True
    # Keys and stems of a data file are its schema. A writer producing another
    # data file with the same keys is authoring a sibling, not naming this one.
    writer = ti.get('file_path') or ti.get('notebook_path') or ''
    if change.get('data_form') and ntpath.splitext(writer)[1].lstrip('.').lower() in CONFIG_SUFFIXES:
        return False
    return any(contains(text, alias, 'identifier') for alias in change['aliases'])


def simple_argv(command):
    """No guessed branch selection or shell expansion from an aggregate output."""
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=';&|()<>\n')
        lex.whitespace_split = True
        words = list(lex)
    except ValueError:
        return []
    if any(word and all(c in ';&|()<>\n' for c in word) for word in words):
        return []
    while words and (re.match(r'^[A-Za-z_]\w*=', words[0]) or words[0] in ('env', 'command', 'exec')):
        words = words[1:]
    # Substitution and globbing cannot identify an executed path deterministically.
    if any(any(c in word for c in '$*?`') for word in words):
        return []
    return words


def execution_subjects(pre, changes, post=None):
    """Subjects actually invoked by a simple native call or host observation.

    makoto.invocation.subject/subjects are host-owned actual execution targets,
    not arbitrary mentions in tool_input or assistant-produced receipts.
    """
    targets = []
    for event in (pre, post or {}):
        meta = event.get('makoto', {}).get('invocation', {})
        targets.extend(meta.get('subjects', []))
        if meta.get('subject'):
            targets.append(meta['subject'])
    tool, ti = pre.get('tool_name'), pre.get('tool_input', {})
    if tool in ('Run', 'Execute', 'NotebookExecute', 'NotebookRun'):
        targets.extend(ti[key] for key in ('file_path', 'notebook_path', 'script', 'path') if ti.get(key))
    elif tool == 'Bash':
        words = simple_argv(ti.get('command', ''))
        redirects = []
        if not words:
            parsed = redirected_argv(ti.get('command', ''))
            if parsed:
                words = simple_argv(shlex.join(parsed[0]))
                redirects = parsed[1]
        # The launcher records the script payload after --. The normal parser
        # keeps interpreter check/eval flags and output requirements intact.
        launcher = words[1:] if words and program_name(words[0]) in ('sh', 'bash', 'zsh') else words
        if (len(launcher) >= 4 and program_name(launcher[0]) == 'codex-job.sh'
                and launcher[1] == 'start' and '--' in launcher[3:]):
            payload = launcher[launcher.index('--', 3) + 1:]
            if payload:
                nested = dict(pre, tool_input=dict(ti, command=shlex.join(payload)))
                targets.extend(s.removeprefix('file:') for s in execution_subjects(nested, changes, post))
        if words:
            program = program_name(words[0])
            if RUNTIMES.fullmatch(program):
                args = words[1:]
                operand_flags = {'-W', '-X', '--require', '-r', '--loader', '--import', '--input-type', '--conditions', '--inspect-port'}
                i = 0
                while i < len(args):
                    arg = args[i]
                    if arg == '--':
                        i += 1
                        if i < len(args) and args[i] != '-':
                            targets.append(args[i])
                        break
                    if not arg.startswith('-'):
                        targets.append(arg)
                        break
                    # Only interpreter options, before the script/module operand,
                    # select eval/help/check mode; script arguments never do.
                    if program.startswith(('python', 'pypy')) and arg == '-c' and i + 1 < len(args):
                        # Only unconditional, top-level import syntax identifies
                        # modules run by an inline Python invocation.
                        try:
                            body = ast.parse(args[i + 1]).body
                        except SyntaxError:
                            body = []
                        modules = []
                        for statement in body:
                            if isinstance(statement, ast.Import):
                                modules.extend(alias.name for alias in statement.names)
                            elif isinstance(statement, ast.ImportFrom) and not statement.level and statement.module:
                                modules.append(statement.module)
                            else:
                                # Explicit whole-file config consumption, with
                                # no arbitrary call/conditional before the load.
                                expression = statement.value if isinstance(statement, ast.Expr) else None
                                if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name) and expression.func.id == 'print' and len(expression.args) == 1 and not expression.keywords:
                                    expression = expression.args[0]
                                if (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute)
                                        and isinstance(expression.func.value, ast.Name)
                                        and expression.func.value.id in ('json', 'tomllib') and expression.func.attr == 'load'
                                        and len(expression.args) == 1 and not expression.keywords):
                                    opened = expression.args[0]
                                    if (isinstance(opened, ast.Call) and isinstance(opened.func, ast.Name)
                                            and opened.func.id == 'open' and not opened.keywords
                                            and 1 <= len(opened.args) <= 2 and isinstance(opened.args[0], ast.Constant)
                                            and isinstance(opened.args[0].value, str)
                                            and (len(opened.args) == 1 or isinstance(opened.args[1], ast.Constant)
                                                 and opened.args[1].value in ('r', 'rb'))):
                                        path = opened.args[0].value
                                        if path and changes.get(identity(path, pre), {}).get('data'):
                                            targets.append(path)
                                break  # Earlier arbitrary code may exit/raise.
                        for module in modules:
                            candidates = [identity(module.replace('.', '/') + ending, pre)
                                          for ending in ('.py', '/__init__.py')]
                            matches = [value for value in candidates if value in changes]
                            if len(matches) == 1:
                                targets.append(matches[0].removeprefix('file:'))
                        break
                    if program in ('node', 'nodejs') and arg in ('-e', '--eval') and i + 1 < len(args):
                        literal = r'(\x27[^\x27\\]*\x27|"[^"\\]*")'
                        vm = re.fullmatch(r'''\s*require\(['"](?:node:)?vm['"]\)\.runInNewContext\(\s*require\(['"](?:node:)?fs['"]\)\.readFileSync\(\s*'''
                                          + literal + r'''\s*,\s*['"]utf8['"]\s*\)\s*,\s*\{\s*console\s*\}\s*\)\s*;?\s*''', args[i + 1])
                        if vm:
                            targets.append(vm[1][1:-1])
                        break
                    if arg == '-' or arg.startswith(('-c', '-e', '--eval', '--print')) or arg in ('-p', '--help', '-h', '--version', '-V', '--check'):
                        break
                    if program in ('bash', 'sh', 'zsh', 'fish') and (re.fullmatch(r'-[A-Za-z]*[cns][A-Za-z]*', arg) or arg == '--noexec'):
                        break
                    if program.startswith(('python', 'pypy')) and arg.startswith('-m'):
                        module = arg[2:] if arg != '-m' else args[i + 1] if i + 1 < len(args) else ''
                        if re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', module):
                            path = module.replace('.', '/')
                            candidates = [identity(path + ending, pre) for ending in ('.py', '/__main__.py')]
                            matches = [value for value in candidates if value in changes]
                            if len(matches) == 1:
                                targets.append(matches[0].removeprefix('file:'))
                            if module == 'pytest':
                                remaining = args[i + (1 if arg != '-m' else 2):]
                                targets.extend(w.split('::')[0] for w in remaining if not w.startswith('-'))
                        break
                    i += 2 if arg in operand_flags else 1
            elif program in ('sqlite3', 'psql', 'mysql'):
                targets.extend(target for operator, target in redirects if operator == '<'
                               and not any(c in target for c in '$*?`'))
                if program == 'psql' and '-f' in words and words.index('-f') + 1 < len(words):
                    targets.append(words[words.index('-f') + 1])
            elif program in ('awk', 'gawk', 'mawk', 'nawk'):
                for i, word in enumerate(words[1:], 1):
                    if word in ('-f', '--file') and i + 1 < len(words):
                        targets.append(words[i + 1])
                    elif word.startswith('--file='):
                        targets.append(word.split('=', 1)[1])
                    elif word.startswith('-f') and len(word) > 2:
                        targets.append(word[2:])
            elif program == 'go' and len(words) > 2 and words[1] == 'run':
                targets.extend(w for w in words[2:] if w.endswith('.go') and not w.startswith('-'))
            elif program == 'jupyter' and len(words) > 2 and words[1] == 'nbconvert' and '--execute' in words[2:]:
                targets.extend(w for w in words[2:] if w.endswith('.ipynb') and not w.startswith('-'))
            elif program in ('.', 'source') and len(words) > 1:
                targets.append(words[1])
            elif program not in ('cat', 'head', 'tail', 'less', 'more', 'wc', 'rg', 'grep', 'ls', 'stat', 'find', 'echo', 'printf', 'touch', 'cp', 'mv', 'rm', 'sed', 'tee'):
                # Direct executables are a program position, never an argument.
                targets.append(words[0])
                if program in ('pytest', 'py.test'):
                    targets.extend(w.split('::')[0] for w in words[1:] if not w.startswith('-'))
                # Config consumption is explicit option syntax, not any mention.
                for i, word in enumerate(words[1:], 1):
                    if word == '--config' and i + 1 < len(words):
                        targets.append(words[i + 1])
                    elif word.startswith('--config='):
                        targets.append(word.split('=', 1)[1])
    return {identity(target, pre) for target in targets if target != ''}


def compiled_subjects(pre):
    """An explicit native compiler source -> -o product link, never a run."""
    words = simple_argv(pre.get('tool_input', {}).get('command', ''))
    if not words:
        return None
    program = program_name(words[0])
    if program not in ('cc', 'gcc', 'clang', 'c++', 'g++', 'clang++', 'rustc'):
        return None
    if any(w in ('-c', '-S', '-E', '-fsyntax-only', '--emit=metadata') for w in words):
        return None
    if '-o' not in words or words.index('-o') + 1 >= len(words):
        return None
    output = words[words.index('-o') + 1]
    sources = [w for w in words[1:] if w != output and not w.startswith('-')
               and ntpath.splitext(w)[1] in ('.c', '.cc', '.cpp', '.cxx', '.rs')]
    if not output or not sources:
        return None
    return identity(output, pre), {identity(source, pre) for source in sources}


def run_output(post):
    """An error response counts; an absent response or launch receipt does not."""
    response = post.get('tool_response')
    if response is None:
        return False
    if isinstance(response, dict):
        if response.get('backgroundTaskId') or response.get('session_id') or response.get('sessionId') or response.get('running'):
            return any(isinstance(response.get(key), str) and bool(response[key])
                       for key in ('stdout', 'stderr', 'output'))
        # The host's returned status is a response even for a silent program.
        return any(key in response for key in ('stdout', 'stderr', 'output', 'content', 'exitCode', 'exit_code', 'exit'))
    return isinstance(response, (str, list))


# ======================================================================
# shipping: Commit scope from recorded git arguments and successful staging receipts.
#
# Never invokes git or assumes all session edits belong to a commit.

def git_calls(event):
    cwd = event.get('cwd') or '/'
    for words in programs(event):
        if program_name(words[0]) == 'cd' and len(words) == 2:
            cwd = normalized_path(words[1], cwd)
            continue
        if program_name(words[0]) != 'git':
            continue
        context_cwd, i = cwd, 1
        while i < len(words) and words[i].startswith('-'):
            option = words[i]
            if option in ('-C', '-c', '--git-dir', '--work-tree'):
                if i + 1 >= len(words):
                    break
                if option == '-C':
                    context_cwd = normalized_path(words[i + 1], context_cwd)
                i += 2
            else:
                i += 1
        if i < len(words):
            yield dict(event, cwd=context_cwd), words[i], list(words[i + 1:])


def operands(args):
    result, i = [], 0
    value_options = {'-m', '--message', '-F', '--file', '-C', '-c', '--reuse-message',
                     '--reedit-message', '--fixup', '--squash', '--author', '--date',
                     '--cleanup', '--pathspec-from-file', '--unified'}
    while i < len(args):
        word = args[i]
        if word == '--':
            return result + args[i + 1:]
        if word in value_options:
            i += 2
            continue
        if re.fullmatch(r'-[a-zA-Z]*[mF]', word):
            i += 2
            continue
        if not word.startswith('-'):
            result.append(word)
        i += 1
    return result


def matches(subject, specs, event):
    if not subject.startswith('file:'):
        return False
    path = subject[5:]
    for spec in specs:
        if any(c in spec for c in '$`') or spec.startswith(':'):
            continue  # An opaque pathspec declares no concrete file here.
        target = normalized_path(spec, event['cwd'])
        if path == target or path.startswith(target.rstrip('/') + '/') or fnmatch.fnmatchcase(path, target):
            return True
    return False


def commit_changes(ledger, event, changes=None):
    """None for nonshipping calls, otherwise the recorded commit's code forms."""
    result, shipping = {}, False
    changes = ledger.changed_code() if changes is None else changes
    staged = dict(ledger.staged_code)
    for context, action, args in git_calls(event):
        specs = operands(args)
        # A proposed aggregate command can stage or unstage before committing.
        # This predicts its file selection, never invents a completed run or
        # mutates the ledger with candidate evidence.
        if action == 'add' and not any(a in args for a in ('--dry-run', '-n', '--intent-to-add', '-N', '-p', '--patch', '-i', '--interactive')):
            if '--all' in args or '-A' in args or ('-u' in args or '--update' in args) and not specs:
                specs = ['.']
            staged.update({s: c for s, c in changes.items() if matches(s, specs, context)})
        elif action in ('reset', 'restore', 'rm') and (action != 'restore' or '--staged' in args or '-S' in args):
            staged = {s: c for s, c in staged.items() if specs and not matches(s, specs, context)}
        if action not in ('commit', 'push'):
            continue
        shipping = True
        if action == 'push':
            result.update(ledger.committed_code)
            continue
        if any(a in args for a in ('--dry-run', '--short', '--porcelain')):
            continue
        only = '--only' in args or '-o' in args or specs and '--include' not in args and '-i' not in args
        selected = {} if only else dict(staged)
        if specs:
            selected.update({s: c for s, c in changes.items() if matches(s, specs, context)})
        if '--all' in args or any(re.fullmatch(r'-[a-zA-Z]*a[a-zA-Z]*', a) for a in args):
            selected.update({s: c for s, c in changes.items() if s in ledger.git_tracked})
        result.update(selected)
    return result if shipping else None


def record_git(ledger, pre, post):
    if failed(post) or post.get('tool_response') is None or pre.get('tool_name') != 'Bash':
        return
    response = post['tool_response']
    if isinstance(response, dict) and any(response.get(k) for k in
            ('backgroundTaskId', 'session_id', 'sessionId', 'running', 'truncated', 'is_truncated')):
        return
    segments = selected_segments(pre.get('tool_input', {}).get('command', ''), post)
    if segments is None:
        return
    cwd = pre.get('cwd') or '/'
    for command in segments:
        act = dict(pre, cwd=cwd, tool_input=dict(pre.get('tool_input', {}), command=command))
        for words in programs(act):
            if program_name(words[0]) == 'cd' and len(words) == 2:
                cwd = normalized_path(words[1], cwd)
        for context, action, args in git_calls(act):
            specs = operands(args)
            if action == 'add' and not any(a in args for a in ('--dry-run', '-n', '--intent-to-add', '-N', '-p', '--patch', '-i', '--interactive')):
                if '--all' in args or '-A' in args or ('-u' in args or '--update' in args) and not specs:
                    specs = ['.']
                for subject, change in ledger.changed_code().items():
                    if matches(subject, specs, context):
                        ledger.staged_code[subject] = dict(change)
                        ledger.git_tracked.add(subject)
            elif action in ('reset', 'restore', 'rm') and (action != 'restore' or '--staged' in args or '-S' in args):
                for subject in list(ledger.staged_code):
                    if not specs or matches(subject, specs, context):
                        ledger.staged_code.pop(subject, None)
            elif action == 'commit' and not any(a in args for a in ('--dry-run', '--short', '--porcelain')):
                committed = commit_changes(ledger, act)
                ledger.committed_code.update(committed)
                for subject in committed:
                    ledger.staged_code.pop(subject, None)
            # A single status/diff receipt attributes returned names to this git
            # query. Aggregate shell stdout cannot identify which call owned it.
            elif len(segments) == 1 and action in ('status', 'diff', 'ls-files'):
                body = response_text(post['tool_response'])
                staged = []
                if action == 'status' and any(a.startswith('--porcelain') or a in ('-s', '--short') for a in args):
                    for line in body.replace('\0', '\n').splitlines():
                        if len(line) < 4 or line[2] != ' ':
                            continue
                        state, path = line[:2], line[3:].split(' -> ')[-1]
                        try:
                            path = json.loads(path) if path.startswith('"') else path
                        except ValueError:
                            continue
                        subject = ledger.subject(path, context)
                        if state != '??':
                            ledger.git_tracked.add(subject)
                        if state[0] not in (' ', '?', '!'):
                            staged.append(subject)
                elif action == 'diff' and '--name-only' in args and any(a in args for a in ('--cached', '--staged')):
                    staged = [ledger.subject(p, context) for p in body.replace('\0', '\n').splitlines() if p]
                elif action == 'ls-files':
                    ledger.git_tracked.update(ledger.subject(p, context) for p in body.replace('\0', '\n').splitlines() if p)
                for subject in staged:
                    change = ledger.changed_code().get(subject)
                    if change:
                        ledger.staged_code[subject] = dict(change)
                complete_scope = (action == 'status' and not specs or action == 'diff'
                                  and '--name-only' in args and not specs
                                  and any(a in args for a in ('--cached', '--staged')))
                if complete_scope:
                    for subject in list(ledger.staged_code):
                        if matches(subject, ['.'], context) and subject not in staged:
                            ledger.staged_code.pop(subject)


# ======================================================================
# creations: Syntactic introductions in native writes, without treating them as readings.

def introduces(ledger, event):
    if event.get('tool_name') not in WRITERS:
        return False
    ti = event.get('tool_input', {})
    text = '\n'.join(ti.get(k, '') for k in ('content', 'new_string', 'new_source'))
    target = ti.get('file_path') or ti.get('notebook_path')
    if not target or not text.strip():
        return False
    # Existing names and located references retain their independent holds.
    prior = ledger.given + [t for r in ledger.readings + ledger.inputs for t in r['texts']]
    for span in names(text):
        if span.kind in ('path', 'url', 'external-package') or any(contains(t, span.text, span.kind) for t in prior):
            return False
    try:
        tree = ast.parse(text)
        if any(isinstance(n, (ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.ClassDef)) for n in tree.body):
            return True
    except SyntaxError:
        pass
    if re.fullmatch(r'(?:[A-Za-z_]\w*=[^\n]*\n?)+', text):
        return True
    if ntpath.splitext(target)[1] in ('.sh', '.bash', '.zsh'):
        return ordered_segments(text) is not None
    return False


# ======================================================================
# provenance: Agnostic ordered sweep: source bytes, own output, writes, and online calls.

class Ledger:
    def __init__(self):
        self.q = 0
        self.turn = '0'
        self.pending = {}
        self.pending_order = {}
        self.denied = {}
        self.seen = set()
        self.given = []
        self.readings = []
        self.inputs = []
        self.written = set()
        self.tainted = set()
        self.mutations = {}
        self.reservations = {}
        self.online = []
        self.external = []
        self.own = []
        self.unknown = []
        self.code_changes = {}
        self.executions = []
        self.readbacks = []
        self.shebangs = set()
        self.compiled = {}
        self.staged_code = {}
        self.git_tracked = set()
        self.committed_code = {}

    def changed_code(self):
        result = dict(self.code_changes)
        for tid, pre in self.pending.items():
            for effect in effects(pre):
                if effect.get('removed') or effect.get('renamed_from'):
                    continue
                form = edited_forms(pre, effect['subject'])
                if form:
                    subject = form['subject']
                    prior = result.get(subject, {})
                    form['aliases'] |= prior.get('aliases', set())
                    form['data'] = form['data'] and subject not in self.shebangs and prior.get('data', True)
                    form['q'] = self.pending_order[tid]
                    form['agent'] = pre.get('agent_id')
                    if form['q'] > prior.get('q', 0):
                        result[subject] = form
        # Records never run. Keep their observed forms internally so a shebang
        # seen before a shell edit can still establish a script obligation.
        return {subject: form for subject, form in result.items()
                if not (form.get('record') and form.get('data'))}

    def change_code(self, event, subject):
        rename = next((effect for effect in effects(event)
                       if effect.get('renamed_from') and self.subject(effect['subject'], event) == subject), None)
        if rename:
            source = self.subject(rename['renamed_from'], event)
            prior = self.code_changes.get(source)
            if prior:
                form = edited_forms(event, rename['subject'])
                aliases = prior['aliases'] | (form['aliases'] if form else set())
                self.code_changes[subject] = dict(prior, subject=subject, display=rename['subject'], aliases=aliases)
                for run in self.executions + self.readbacks:
                    # A prior run of the overwritten destination is a different
                    # program. Only source witnesses travel with the rename.
                    run['subjects'] = run['subjects'] - {subject}
                    if source in run['subjects']:
                        run['subjects'] = run['subjects'] | {subject}
                self.shebangs.discard(subject)
                if source in self.shebangs:
                    self.shebangs.add(subject)
            # A rename moves an existing obligation; it does not author code.
            return
        if any(effect.get('removed') and self.subject(effect['subject'], event) == subject for effect in effects(event)):
            self.code_changes.pop(subject, None)
            self.shebangs.discard(subject)
            # Removing a directory removes every edit recorded beneath it.
            prefix = subject.rstrip('/') + '/'
            for under in [s for s in self.code_changes if s.startswith(prefix)]:
                self.code_changes.pop(under)
                self.shebangs.discard(under)
            for staged in [s for s in self.staged_code if s == subject or s.startswith(prefix)]:
                self.staged_code.pop(staged)
            return
        spelling = next((effect['subject'] for effect in effects(event)
                         if self.subject(effect['subject'], event) == subject), subject)
        form = edited_forms(event, spelling)
        if form or subject in self.code_changes:
            prior = self.code_changes.get(subject, {})
            form = form or dict(prior)
            form['aliases'] = form['aliases'] | prior.get('aliases', set())
            replacement = event.get('tool_input', {}).get('content')
            full_write = event.get('tool_name') == 'Write' and isinstance(replacement, str)
            if full_write:
                if re.search(r'(?m)^#!\s*\S+', replacement):
                    self.shebangs.add(subject)
                else:
                    self.shebangs.discard(subject)
            form['data'] = form['data'] and subject not in self.shebangs and (full_write or prior.get('data', True))
            form['q'] = self.q
            form['tool_use_id'] = event.get('tool_use_id')
            form['agent'] = event.get('agent_id')
            self.code_changes[subject] = form

    def run_witnesses(self, change):
        return [run for run in self.executions if run['started'] > change['q']
                and change['subject'] in run['subjects']
                and not any(change['subject'] in self.reservations.get(tid, set()) for tid in self.pending)]

    def readback_witnesses(self, change):
        if not change.get('data') or change['subject'] in self.shebangs:
            return []
        return [read for read in self.readbacks if read['started'] > change['q']
                and change['subject'] in read['subjects']
                and not any(change['subject'] in self.reservations.get(tid, set()) for tid in self.pending)]

    def subject(self, value, event):
        return identity(value, event)

    def fresh(self, item):
        return all(self.mutations.get(s, 0) < item['q'] and not any(s in targets for targets in self.reservations.values()) for s in item['subjects'])

    def source_readings(self):
        return [r for r in self.readings if r['source'] and self.fresh(r)]

    def bash_order(self, pre, post, started, no_effect):
        """Apply lexical acts inside one paired call at distinct positions.

        Original read existence is independent of subsequent file changes;
        aggregate bytes still use the ordinary freshness guard for rule b.
        """
        if pre.get('tool_name') != 'Bash':
            return False
        segments = selected_segments(pre.get('tool_input', {}).get('command', ''), post)
        if segments is None:
            return False
        tid = pre['tool_use_id']
        for index, command in enumerate(segments):
            position = self.q + (index + 1) / (len(segments) + 1)
            segment = dict(pre, tool_input=dict(pre.get('tool_input', {}), command=command))
            # Host observations describe the whole call, never every segment.
            segment.pop('makoto', None)
            subjects = {self.subject(s, pre) for s in reading_subjects(segment)}
            original = subjects - (self.written | self.tainted)
            original -= set().union(*(s for key, s in self.reservations.items() if key != tid))
            response = post.get('tool_response')
            if (len(segments) > 1 and original and bool(list(leaves(response)))
                    and not (isinstance(response, dict) and any(response.get(key)
                             for key in ('backgroundTaskId', 'session_id', 'sessionId', 'running')))
                    and not any(r.get('producer') or r.get('role') == 'relay'
                                for ev in (pre, post) for r in ev.get('makoto', {}).get('reads', []))):
                self.readings.append({'q': position, 'subjects': [], 'texts': [],
                                      'source': True, 'tool_use_id': tid, 'tool': 'Bash',
                                      'turn': self.turn, 'original_subjects': sorted(original)})
            if not no_effect:
                for effect in effects(segment):
                    subject = self.subject(effect['subject'], pre)
                    self.mutations[subject] = position
                    self.written.add(subject)
                    self.compiled.pop(subject, None)
                    self.change_code(segment, subject)
                    if subject in self.code_changes and not effect.get('renamed_from'):
                        self.code_changes[subject]['q'] = position
            if run_output(post):
                compiled = compiled_subjects(segment)
                if compiled and not failed(post):
                    product, sources = compiled
                    self.compiled[product] = {'subjects': sources, 'q': position,
                                              'starts': {s: position if self.code_changes.get(s, {}).get('tool_use_id') == tid
                                                         else started for s in sources}}
                invoked = execution_subjects(segment, self.code_changes)
                if invoked:
                    for subject in invoked:
                        run_start = position if self.code_changes.get(subject, {}).get('tool_use_id') == tid else started
                        self.executions.append({'q': position, 'started': run_start,
                                                'subjects': {subject}, 'tool_use_id': tid})
                    for product in invoked:
                        build = self.compiled.get(product)
                        if build and build['q'] < position:
                            for subject in build['subjects']:
                                self.executions.append({'q': position, 'started': build['starts'][subject],
                                                        'subjects': {subject}, 'tool_use_id': tid})
            complete = full_read_subjects(segment, post)
            if complete:
                for subject in complete:
                    read_start = position if self.code_changes.get(subject, {}).get('tool_use_id') == tid else started
                    self.readbacks.append({'q': position, 'started': read_start,
                                           'subjects': {subject}, 'tool_use_id': tid})
        return True

    def witnesses(self, span, kind=None):
        if any(contains(text, span, kind) for text in self.given):
            return [{'given': True}]
        parts = package_parts(span) if kind == 'external-package' else None

        def seen(text):
            if contains(text, span, kind):
                return True
            # `codex 0.162.0` is the product name of `codex-cli 0.162.0`: same
            # version, and the shorter name is a whole hyphen part of the longer.
            return bool(parts) and any(
                m['version'] == parts[1] and parts[0] in re.split(r'[-_]', m['package'])
                for m in VERSIONED.finditer(text))
        return [r for r in self.source_readings() + [i for i in self.inputs if self.fresh(i)] if any(seen(text) for text in r['texts'])]

    def fetched(self, span, kind=None):
        parts = package_parts(span)
        return [r for r in self.online if r['turn'] == self.turn and self.fresh(r) and any(
            contains(t, span) or parts and any(package_parts(m.group()) == parts for m in VERSIONED.finditer(t))
            for t in (r.get('targets', []) if span.startswith(('https://', 'http://')) else r['texts']))]

    def ingest(self, event, admitted=True):
        self.q += 1
        name, meta = event['hook_event_name'], event.get('makoto', {})
        if meta.get('turn_id') is not None:
            self.turn = str(meta['turn_id'])
        elif name == 'UserPromptSubmit' and not meta.get('same_turn'):
            self.turn = str(self.q)
        if name in ('UserPromptSubmit', 'Register'):
            self.external.extend(meta.get('external_subjects', []))
        if name in FINAL or name == 'AssistantMessage':
            self.own.extend(v for _, v in leaves(event.get('last_assistant_message', event.get('content', ''))))
        if name == 'UserPromptSubmit':
            self.given.append(event.get('prompt', ''))
        if name == 'PreToolUse':
            tid = event.get('tool_use_id')
            if not admitted:
                self.denied.setdefault(tid, event)
                return
            if tid in self.pending or tid in self.seen:
                return
            targets = {self.subject(r['subject'], event) for r in effects(event)}
            self.pending[tid] = event
            self.pending_order[tid] = self.q
            self.reservations[tid] = targets
            if event.get('tool_name') not in WRITERS and not targets and event.get('tool_name') not in ('Agent', 'Task'):
                self.inputs.append({'q': self.q, 'subjects': [self.subject(s, event) for s in reading_subjects(event)],
                                    'texts': list(fragments(event.get('tool_input', {}))), 'tool_use_id': tid})
            return
        if name not in ('PostToolUse', 'PostToolUseFailure'):
            return  # Assistant text, even a paid final, never supplies evidence.
        tid = event.get('tool_use_id')
        pre = self.pending.get(tid)
        if pre is None and tid in self.denied and tid not in self.seen:
            denied = self.denied[tid]
            if (event.get('tool_name', denied.get('tool_name')) == denied.get('tool_name')
                    and ('tool_input' not in event or event['tool_input'] == denied.get('tool_input', {}))
                    and meta.get('no_effect') is not True and not refused(event)):
                # A host-reported completion after denial cannot pay evidence,
                # but its mutation must invalidate old reads and taint readbacks.
                for effect in effects(denied) + effects(event):
                    subject = self.subject(effect['subject'], denied)
                    self.mutations[subject] = self.q
                    self.tainted.add(subject)
                    self.change_code(denied, subject)
                self.seen.add(tid)
        if pre is None or tid in self.seen or event.get('tool_name', pre.get('tool_name')) != pre.get('tool_name') or 'tool_input' in event and event['tool_input'] != pre.get('tool_input', {}):
            self.unknown.append({'q': self.q, 'reason': 'unpaired, replayed or mismatched tool result'})
            return
        del self.pending[tid]
        started = self.pending_order.pop(tid)
        self.seen.add(tid)
        targets = self.reservations.get(tid, set()) | {self.subject(r['subject'], pre) for r in effects(event)}
        no_effect = meta.get('no_effect') is True or refused(event)
        ordered = self.bash_order(pre, event, started, no_effect)
        native = dict(pre)
        native.pop('makoto', None)
        native_targets = {self.subject(r['subject'], pre) for r in effects(native)} if ordered else set()
        if not no_effect:
            for subject in targets:
                if subject in native_targets:
                    continue
                self.mutations[subject] = self.q
                self.written.add(subject)
                self.change_code(pre, subject)
        if not failed(event) or no_effect:
            self.reservations.pop(tid, None)
        record_git(self, pre, event)
        # Paired call plus returned response proves the act, even on failure.
        # Resolve the invocation against its recorded cwd, never final prose.
        if run_output(event) and (not ordered or pre.get('makoto', {}).get('invocation') or meta.get('invocation')):
            invoked = execution_subjects(pre, self.code_changes, event)
            if invoked:
                self.executions.append({'q': self.q, 'started': started,
                                        'subjects': invoked, 'tool_use_id': tid})
        complete = full_read_subjects(pre, event)
        if complete and pre.get('tool_name') not in WRITERS | {'Agent', 'Task'}:
            if not ordered or pre.get('makoto', {}).get('reads') or meta.get('reads'):
                self.readbacks.append({'q': self.q, 'started': started,
                                       'subjects': complete, 'tool_use_id': tid})
            shebang = bool(re.search(r'(?m)^#!\s*\S+', response_text(event.get('tool_response'))))
            for subject in complete:
                change = self.code_changes.get(subject)
                if change and started <= change['q']:
                    continue
                if shebang:
                    self.shebangs.add(subject)
                else:
                    self.shebangs.discard(subject)
                if change and change.get('data_form'):
                    change['data'] = not shebang
        response = event.get('tool_response')
        if response is None or isinstance(response, dict) and response.get('backgroundTaskId'):
            return
        subjects = [self.subject(s, pre) for s in reading_subjects(pre)]
        subjects += [self.subject(r['subject'], pre) for r in meta.get('reads', [])]
        texts = list(fragments(response))
        content_present = bool(list(leaves(response)))
        tool = pre.get('tool_name')
        # A completed run reads an external response, even if it also mutates
        # something. Direct readbacks of session-written files remain own output.
        source = tool not in WRITERS | {'Agent', 'Task'} and not any(s in self.written | self.tainted for s in subjects)
        for spec in meta.get('reads', []) + pre.get('makoto', {}).get('reads', []):
            if spec.get('role') == 'relay' or spec.get('producer'):
                source = False
        # Expand only references actually present in this response, never a store scan.
        if source:
            store = meta.get('detio_store') or pre.get('makoto', {}).get('detio_store') or os.environ.get('DETIO_STORE_DIR')
            for text in list(texts):
                refs = re.findall(r'detio://([0-9a-f]{64}|[0-9a-f]{12})(?![0-9a-f])', text)
                if store:
                    refs += re.findall(re.escape(str(os.path.expanduser(store)).rstrip('/') + '/objects/') + r'([0-9a-f]{64}|[0-9a-f]{12})(?![0-9a-f])', text)
                for address in refs:
                    if not store:
                        raise ValueError('DetIO reference needs a recorded store directory')
                    texts.append(get(store, address))
        item = {'q': self.q, 'subjects': subjects, 'texts': texts,
                'source': source, 'tool_use_id': tid, 'tool': tool, 'turn': self.turn}
        # Empty file content is a reading; empty writer acknowledgments are not.
        if content_present:
            self.readings.append(item)
        if not source:
            self.own.extend(texts)
            self.own.extend(v for _, v in leaves(pre.get('tool_input', {})))
        if source and not failed(event):
            network = network_targets(pre, event)
            if network and content_present:
                self.online.append(dict(item, targets=network, texts=network + texts))


# ======================================================================
# evaluate: Four pre-step holds derived only from literal session observations.

# A dotted name that ends in one of these and is not called is a file name, not an attribute.
FILE_SUFFIXES = frozenset('''md txt json jsonl ndjson tsv csv yaml yml toml ini cfg xml html css sql py sh bash js mjs
    ts tsx jsx ipynb pdf png jpg gif svg zip tar gz'''.split())


def evaluate(ledger, event, adapter='inferred'):
    if adapter != 'inferred':
        raise ValueError('adapter must be inferred')
    text = text_of(event)
    shipping = commit_changes(ledger, event) if event.get('tool_name') == 'Bash' else None
    if shipping is not None:
        # Git options, identity and path selection are operation syntax. Only
        # commit messages make authored claims; d checks the recorded revisions.
        messages = []
        for _, action, args in git_calls(event):
            if action != 'commit':
                continue
            for i, arg in enumerate(args):
                if arg in ('-m', '--message') or re.fullmatch(r'-[a-zA-Z]*m', arg):
                    if i + 1 < len(args):
                        messages.append(args[i + 1])
                elif arg.startswith('--message='):
                    messages.append(arg.split('=', 1)[1])
        text = '\n'.join(messages)
    creation = introduces(ledger, event)
    readings = ledger.source_readings()
    findings, snapshot = [], []
    spans = extract(text)
    name_spans = [] if creation else names(text)
    output_subjects = ledger.written | {ledger.subject(r['subject'], event) for r in effects(event)}
    output_ranges = []
    # Whitespace in an output filename can split lexical tokens. Exempt those
    # slices only within a complete output path, with exact token boundaries.
    for subject in output_subjects:
        if subject.startswith('file:') and ' ' in subject:
            absolute = subject[5:]
            for path in path_spellings(absolute, event.get('cwd') or os.getcwd()):
                pattern = r'(?<![\w/\\.@:+~%#?=&$!*|-])' + re.escape(path) + r'(?![\w/\\.@:+~%#?=&$!*|-])'
                output_ranges.extend(m.span() for m in re.finditer(pattern, text))

    # An id the write itself defines (first table cell, heading, list label) is
    # authored here, not a reference to something unread. Uses of other ids still hold.
    defined = set(re.findall(r'(?m)^\s*\|\s*\**([A-Za-z][\w.-]*)\**\s*\|', text))
    defined |= set(re.findall(r'(?m)^\s*(?:#+|[-*])\s+\**([A-Za-z][\w.-]*\d)\**(?=[\s:.)]|$)', text))

    # A new script binds its own functions, classes and variables; writing them
    # is authoring, not citing something unread. Only code files qualify.
    authored = set()
    target = (event.get('tool_input') or {}).get('file_path') or ''
    if event.get('tool_name') == 'Write' and re.search(r'\.(?:py|sh|bash|js|mjs|ts)$', target):
        defined |= set(re.findall(r'(?m)^[ \t]*(?:async\s+)?(?:def|class|function)\s+([A-Za-z_]\w*)', text))
        defined |= set(re.findall(r'(?m)^[ \t]*(?:(?:export\s+)?(?:const|let|var)\s+)?([A-Za-z_]\w*)\s*=(?!=)', text))
        defined |= set(re.findall(r'(?m)^[ \t]*for\s+([A-Za-z_]\w*)\s+in\b', text))
        # The interpreter line and the file's own name are authored here too.
        # Any other path in the text, even a constant, still needs a reading.
        shebang = re.search(r'(?m)^#!(\S+)(?:[ \t]+(\S+))?', (event.get('tool_input') or {}).get('content') or '')
        shebang = shebang if shebang and shebang.start() == 0 else None
        if shebang:
            authored |= {'#!' + shebang.group(1), *( [shebang.group(2)] if shebang.group(2) else [] )}
            defined |= set(filter(None, [shebang.group(2)]))
        authored.add(os.path.basename(target))

    # In an edit of a code file, `row.get` or `new.items` is an attribute chain
    # on a name the code already has: bound in the edited text, or present in
    # the file this turn read. A file-suffix tail (`row.md`) is still a path.
    code_roots = set()
    if event.get('tool_name') in WRITERS and re.search(r'\.(?:py|sh|bash|js|mjs|ts)$', target):
        file_subject = ledger.subject(target, event)
        file_texts = [t for r in readings if file_subject in r['subjects'] for t in r['texts']]
        bound = set(defined)
        # Names the edited text binds: assignments, parameters, imports, `as` and loop targets.
        bound |= set(re.findall(r'(?m)^[ \t]*([A-Za-z_]\w*)\s*=(?!=)', text))
        bound |= {w for args in re.findall(r'(?m)^[ \t]*(?:async\s+)?def\s+\w+\s*\(([^)]*)\)', text)
                  for a in args.split(',') for w in re.findall(r'^\s*\*{0,2}([A-Za-z_]\w*)', a)}
        bound |= set(re.findall(r'(?m)^[ \t]*(?:import|from)\s+([A-Za-z_]\w*)', text))
        bound |= set(re.findall(r'\bas\s+([A-Za-z_]\w*)', text))
        bound |= {w for tup in re.findall(r'(?m)^[ \t]*for\s+([^:\n]+?)\s+in\b', text)
                  for w in re.findall(r'[A-Za-z_]\w*', tup)}
        bound |= {w for tup in re.findall(r'(?m)^[ \t]*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)+)\s*=(?!=)', text)
                  for w in re.findall(r'[A-Za-z_]\w*', tup)}
        code_roots = bound | {w for w in set(re.findall(r'[A-Za-z_]\w*', text))
                              if any(contains(t, w, 'identifier') for t in file_texts)}

    def attribute_chain(span):
        root, *tail = span.text.split('.')
        return (span.kind == 'path' and len(tail) > 0 and re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+', span.text)
                and root in code_roots
                and (tail[-1].lower() not in FILE_SUFFIXES or text[span.end:span.end + 1] == '('))

    def output_name(span):
        if span.kind == 'identifier' and span.text in defined:
            return True
        if attribute_chain(span):
            return True
        if span.kind == 'path' and (span.text in authored or span.text.rstrip('.') in authored):
            return True
        return span.kind == 'path' and ledger.subject(span.text, event) in output_subjects or any(start <= span.start and span.end <= end for start, end in output_ranges)

    if not readings and not creation and (shipping is None or name_spans):
        span = spans[0].text if spans else text
        findings.append({'rule': 'a', 'family': 'a', 'shape': 'lineage', 'subject': span,
                         'missing': 'ANSWER FROM ITS OWN ANSWER: read an original artifact before this step; assistant text and files this session wrote do not clear it'})
    # Rule a asks whether an original artifact was read. It does not require
    # a derived result or repeated answer to occur verbatim in that artifact.
    # Exact unread names remain governed independently by rule b.
    for span in name_spans:
        cited = span
        if span.kind == 'path' and re.search(r':\d+(?::\d+)?$', span.text):
            # `file.py:12` cites a line of the file: the file read, or the
            # exact citation seen in output, evidences it.
            base = re.sub(r':\d+(?::\d+)?$', '', span.text)
            span = type(span)(base, span.start, span.start + len(base), span.kind)
        if output_name(span):
            snapshot.append({'span': span.text, 'kind': span.kind, 'output': True})
            continue
        witnesses = ledger.witnesses(span.text, span.kind) or ledger.witnesses(cited.text, cited.kind)
        if (span.kind == 'path' and not span.text.startswith('#!')
                and any(contains(t, span.text, span.kind) for t in ledger.given)):
            # Naming a file in the prompt does not read its contents.
            witnesses = [w for w in witnesses if not w.get('given')]
            if not witnesses:
                witnesses = [r for r in ledger.source_readings() if any(contains(t, span.text, span.kind) for t in r['texts'])]
        if not witnesses:
            findings.append({'rule': 'b', 'family': 'b', 'shape': 'spec', 'subject': span.text,
                             'missing': 'NAMED WITHOUT READING: read a source whose tool input or response contains these exact characters; a different spelling or stale reading does not clear it'})
        else:
            snapshot.append({'span': span.text, 'kind': span.kind,
                             'reading_receipt_ids': [w.get('tool_use_id', 'user prompt') for w in witnesses]})
    # A URL built from shell variables is a template, and a shell's own version
    # floor is a local requirement: neither names an outside subject.
    external = [s.text for s in spans + name_spans
                if (s.kind == 'url' and not re.search(r'\$[\w{(]|\{\{|<[a-z_]+>', s.text))
                or s.kind == 'external-package' and re.search(r'@|==|>=|<=|~=|\bversion\s|\sv\d', s.text)
                and not re.match(r'(?:ba|z|da|k)?sh\b', s.text)]
    # An earlier online response can establish a package's external identity;
    # it still needs a fresh online receipt in the current turn.
    for span in spans:
        parts = package_parts(span.text) if span.kind == 'external-package' else None
        if parts and any(contains(t, span.text) for r in ledger.online for t in r['texts']):
            external.append(span.text)
    # Host-classified public projects are checked by the same literal sweep.
    external += [s for s in ledger.external + event.get('makoto', {}).get('external_subjects', []) if contains(text, s)]
    for span in dict.fromkeys(external):
        if not ledger.fetched(span):
            findings.append({'rule': 'c', 'family': 'c', 'shape': 'other point', 'subject': span,
                             'missing': 'DID NOT LOOK ONLINE: fetch or search this exact external subject with WebFetch, WebSearch or a Bash network call in this turn'})
    for change in (shipping if shipping is not None else ledger.changed_code()).values():
        if shipping is None and not names_change(event, change):
            continue
        runs = ledger.run_witnesses(change)
        readbacks = ledger.readback_witnesses(change)
        if not runs and not readbacks:
            findings.append({'rule': 'd', 'family': 'd', 'shape': 'switch',
                             'subject': change['display'],
                             'missing': 'UNRUN CHANGE: run it and read the output before this step'})
        else:
            witnesses = runs or readbacks
            snapshot.append(receipt(change['display'], [run['tool_use_id'] for run in witnesses],
                                    'makoto2.switch/execution-v1' if runs else 'makoto2.switch/readback-v1'))
    if not findings and readings:
        snapshot.append(receipt(text, [r['tool_use_id'] for r in readings], 'makoto2.precision/form-v1'))
    return list({(f['rule'], f['subject']): f for f in findings}.values()), snapshot


# ======================================================================
# hook: Locked append-only hook journal and fail-closed admission transport.

FOUR_QUESTIONS = "Before this step: (1) If it relies on a definition, did you read the thing itself against that definition? (2) If it carries a result to another place or time, did you read the same thing again where and when it lands? (3) If it says how a branch behaves, did you feed that branch an input and read its response? (4) Is it based on the original source, read this turn, rather than on an earlier answer?"


def d_in(raw):
    event = json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    if not isinstance(event, dict) or not isinstance(event.get('hook_event_name'), str) or not event['hook_event_name']:
        raise ValueError('missing hook event')
    if not isinstance(event.get('session_id'), str) or not event['session_id']:
        raise ValueError('missing session identity')
    if not isinstance(event.get('makoto', {}), dict) or not isinstance(event.get('tool_input', {}), dict):
        raise ValueError('makoto and tool_input must be objects')
    meta = event.get('makoto', {})
    for key in ('definitions', 'reads', 'effects', 'obligations', 'dependencies', 'aliases'):
        if key in meta and (not isinstance(meta[key], list) or any(not isinstance(item, dict) for item in meta[key])):
            raise ValueError('makoto.' + key + ' must be an object list')
    for key in ('place', 'destination', 'points', 'invocation'):
        if key in meta and not isinstance(meta[key], dict):
            raise ValueError('makoto.' + key + ' must be an object')
    invocation = meta.get('invocation', {})
    if 'subject' in invocation and (not isinstance(invocation['subject'], str) or not invocation['subject']):
        raise ValueError('makoto.invocation.subject must be a nonempty string')
    if 'subjects' in invocation and (not isinstance(invocation['subjects'], list) or any(not isinstance(s, str) or not s for s in invocation['subjects'])):
        raise ValueError('makoto.invocation.subjects must contain nonempty strings')
    if 'prompt' in event and not isinstance(event['prompt'], str):
        raise ValueError('prompt must be text')
    for key in ('external_subjects', 'network_subjects'):
        if key in meta and (not isinstance(meta[key], list) or any(not isinstance(v, str) or not v for v in meta[key])):
            raise ValueError(key + ' must contain nonempty strings')
    if 'last_assistant_message' in event and not isinstance(event['last_assistant_message'], str):
        raise ValueError('last_assistant_message must be text')
    if event['hook_event_name'] in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure') and (not isinstance(event.get('tool_use_id'), str) or not event['tool_use_id']):
        raise ValueError('tool events require an exact tool_use_id')
    return event


REPORT_LIMIT = 700


def brief(report):
    """Report-only text is advice, not a gate: show the head, keep the count.

    The journal holds every finding; a 20 KB message per write costs the
    session more than the findings tell it.
    """
    if len(report) <= REPORT_LIMIT:
        return report
    return report[:REPORT_LIMIT].rstrip() + ' ... (%d more characters; the full findings are in the journal)' % (len(report) - REPORT_LIMIT)


def sigma_path(state_dir, session_id):
    return Path(state_dir) / (hashlib.sha256(session_id.encode()).hexdigest() + '.jsonl')


@contextlib.contextmanager
def session_lock(path, wait):
    """Exclusive per-session lock, never waited on longer than `wait` seconds (TimeoutError)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait
    with open(str(path) + '.lock', 'a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
            take = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            give = lambda: (stream.seek(0), msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1))
        else:
            import fcntl
            take = lambda: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            give = lambda: fcntl.flock(stream, fcntl.LOCK_UN)
        while True:
            try:
                take()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('session lock busy for %gs' % wait)
                time.sleep(0.02)
        try:
            yield
        finally:
            give()


def sigma_read(path, session_id, cache=None):
    """The verified journal. With a cache, only rows after its offset are read and verified,
    chained to the last verified seal; the cache is extended in place."""
    if cache is None:
        cache = {'offset': 0, 'rows': [], 'last': ''}
    if (path.stat().st_size if path.exists() else 0) < cache['offset']:
        # Truncated or replaced: start over from its first row.
        cache.update(offset=0, rows=[], last='')
    if not path.exists():
        return cache['rows']
    previous = cache['last']
    with path.open('rb') as stream:
        stream.seek(cache['offset'])
        for raw in stream:
            row = json.loads(raw.decode('utf-8'))
            seal = row.pop('sha256')
            if row.get('previous') != previous or seal != hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest():
                raise ValueError('corrupted journal chain')
            if row['event']['session_id'] != session_id:
                raise ValueError('session identity collision')
            previous = seal
            # Only what replay reads; findings and snapshots stay in the file.
            cache['rows'].append({'event': row['event'], 'admitted': row['admitted'], 'sha256': seal,
                                  'stop_hook_active_unpaid': row.get('stop_hook_active_unpaid', False)})
            cache['offset'] += len(raw)
    cache['last'] = previous
    return cache['rows']


# ======================================================================
# checkpoint: the state a call leaves for the next, so each call reads only what is new.
#
# One marshal file beside the journal (marshal builds only plain data, never runs code):
# the journal read so far, the transcript parse so far, and the replayed Ledger with the
# tags of the records it covers. A checkpoint that does not load, or whose records differ
# from this call's, is ignored and the call replays in full.

CHECKPOINT_VERSION = 1


def checkpoint_load(path, session_id):
    try:
        with open(str(path) + '.ckpt', 'rb') as stream:
            state = marshal.load(stream)
        if state.get('version') == CHECKPOINT_VERSION and state.get('session_id') == session_id:
            return state
    except (OSError, EOFError, ValueError, TypeError, AttributeError):
        pass
    return {'version': CHECKPOINT_VERSION, 'session_id': session_id,
            'journal': {'offset': 0, 'rows': [], 'last': ''}, 'transcript': None, 'tags': [], 'ledger': None}


def checkpoint_save(path, blob):
    tmp = str(path) + '.ckpt.tmp'
    try:
        with open(tmp, 'wb') as stream:
            stream.write(blob)
        os.replace(tmp, str(path) + '.ckpt')
    except OSError:
        # Unwritable: the next call replays in full.
        with contextlib.suppress(OSError):
            os.remove(tmp)


def sigma_append(path, row, previous):
    row['previous'] = previous
    row['sha256'] = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def d_out(event, reason):
    if not reason:
        return {}
    if event.get('hook_event_name') == 'PreToolUse':
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': reason}}
    return {'decision': 'block', 'reason': reason}


def questions(event):
    if not dependent(event):
        return {}
    if event['hook_event_name'] == 'PreToolUse':
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'additionalContext': FOUR_QUESTIONS}}
    if not event.get('stop_hook_active'):
        return {'decision': 'block', 'reason': FOUR_QUESTIONS}
    return {}


def in_scope(cwd, prefixes):
    cwd = cwd.replace('\\', '/').rstrip('/').lower()
    for prefix in prefixes:
        prefix = prefix.replace('\\', '/').rstrip('/').lower()
        if prefix and (cwd == prefix or cwd.startswith(prefix + '/')):
            return True
    return False


def held_again(event, journal):
    """True when this active Stop was already held once more this turn: the cap is one repeat."""
    for row in reversed(journal):
        prior = row['event']
        if prior.get('hook_event_name') == 'UserPromptSubmit' and not prior.get('makoto', {}).get('same_turn'):
            return False
        if (prior.get('hook_event_name') == event['hook_event_name'] and prior.get('agent_id') == event.get('agent_id')
                and row.get('stop_hook_active_unpaid')):
            return True
    return False


def replay(records, base):
    """The Ledger after `records`, starting from a checkpointed (count, marshalled state) when given."""
    start, state = base
    # D20: a record that cannot be ingested is unknown, never partial evidence,
    # and never wedges later calls. Replay again without it; rare, so no per-record copy.
    skipped = {}
    while True:
        ledger = Ledger()
        if state is not None:
            ledger.__dict__.update(marshal.loads(state))
        for index in range(start, len(records)):
            prior, admitted, _ = records[index]
            if index in skipped:
                ledger.q += 1
                ledger.unknown.append({'q': ledger.q, 'reason': 'historical ingest failed: ' + skipped[index]})
                continue
            try:
                ledger.ingest(prior, admitted)
            except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
                skipped[index] = str(error)
                break
        else:
            return ledger


def main(raw, config):
    try:
        event = d_in(raw)
        adapter = config.get('adapter', 'inferred')
        if adapter != 'inferred':
            raise ValueError('adapter must be inferred')
        path = sigma_path(config['state_dir'], event['session_id'])
        with session_lock(path, config.get('lock_seconds', 3.0)):
            checkpoint = config.get('checkpoint', True)
            state = checkpoint_load(path, event['session_id']) if checkpoint else None
            journal = sigma_read(path, event['session_id'], state['journal'] if state else None)
            records, transcript = history(event, journal, state['transcript'] if state else None)
            tags = [(tag, admitted) for _, admitted, tag in records]
            base = (0, None)
            if state and state['ledger'] is not None and tags[:len(state['tags'])] == state['tags']:
                base = (len(state['tags']), state['ledger'])
            ledger = replay(records, base)
            if state:
                state['transcript'] = transcript
                try:
                    state['tags'], state['ledger'] = tags, marshal.dumps(ledger.__dict__)
                except ValueError:
                    state['tags'], state['ledger'] = [], None
                # Taken before the candidate touches journal, ledger or events.
                try:
                    saved = marshal.dumps(state)
                except ValueError:
                    state = None
            # Turn metadata on the candidate belongs to this check; its receipts do not.
            if event.get('makoto', {}).get('turn_id') is not None:
                ledger.turn = str(event['makoto']['turn_id'])
            findings, snapshot, contract = [], [], None
            if dependent(event):
                try:
                    findings, snapshot = evaluate(ledger, event, adapter)
                except (KeyError, TypeError, ValueError) as error:
                    contract = str(error)
            reason = None
            if contract:
                reason = 'makoto contract: ' + contract
            elif findings:
                reason = '; '.join('makoto rule ' + f['rule'] + ' [' + f['shape'] + ']: ' + json.dumps(f['subject'], ensure_ascii=False) + ': ' + f['missing'] for f in findings)
            report, capped = None, False
            scope = config.get('block_in')
            if reason and scope and not in_scope(event.get('cwd') or '', scope):
                # Report only outside the listed projects: the step runs, the
                # journal keeps the finding, and nothing blocks.
                report, reason = 'makoto report only (outside block_in): ' + brief(reason), None
            elif reason and event.get('stop_hook_active') and held_again(event, journal):
                # One repeat at most: a Stop already held again this turn is admitted
                # with its findings shown and journaled, so a turn can always end.
                report, reason, capped = 'makoto held this stop once already; not held again: ' + brief(reason), None, True
            row = {'event': event, 'admitted': not bool(reason), 'adapter': adapter,
                   'findings': findings, 'contract_error': contract, 'snapshot': snapshot,
                   'turn_id': ledger.turn, 'stop_hook_active_unpaid': bool(reason and event.get('stop_hook_active')),
                   'stop_cap': capped, 'unknown': ledger.unknown}
            # Validate transitions before persisting invalid host records.
            ledger.ingest(event, row['admitted'])
            sigma_append(path, row, journal[-1]['sha256'] if journal else '')
            if state:
                checkpoint_save(path, saved)
            if report:
                return {'systemMessage': report}
            return d_out(event, reason) if reason else questions(event)
    except Exception as error:
        # Fail open: an infrastructure or transport error (state, lock, journal, transcript,
        # malformed host event) never denies a step; only rule findings above do.
        return {'systemMessage': 'makoto infrastructure error, step allowed: %s: %s' % (type(error).__name__, error)}


# ======================================================================
# __main__: Live entry: python -m makoto2, one serialized native event on stdin.

def run():
    try:
        cfg = dict(CONFIG)
        cfg['state_dir'] = os.path.expanduser(os.environ.get('MAKOTO_STATE_DIR', cfg['state_dir']))
        cfg['adapter'] = os.environ.get('MAKOTO_ADAPTER', cfg['adapter'])
        cfg['lock_seconds'] = float(os.environ.get('MAKOTO_LOCK_SECONDS', cfg['lock_seconds']))
        cfg['checkpoint'] = os.environ.get('MAKOTO_CHECKPOINT', '1') != '0'
        scope = os.environ.get('MAKOTO_BLOCK_IN')
        if scope:
            cfg['block_in'] = [p for p in scope.split(os.pathsep) if p]
        response = main(sys.stdin.read(), cfg)
    except Exception as error:
        response = {'systemMessage': 'makoto infrastructure error, step allowed: %s: %s' % (type(error).__name__, error)}
    sys.stdout.write(json.dumps(response))
    return 0


if __name__ == '__main__':
    sys.exit(run())
