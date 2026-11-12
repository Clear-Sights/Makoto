"""Makoto: holds a final answer that ships a code file edited this session and not run since. Live entry:
cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m makoto2 (hooks/hooks.json), one serialized native Claude Code hook
event on stdin, one JSON response on stdout.

A hook event is appended to a locked, hash-linked journal and replayed, with the host transcript, into a Ledger of
edits, runs and full reads. Only a final answer (Stop, SubagentStop, PreDelivery) can be held, by rule d, and only
a run of the file, a run of a program that imports it, or (for a config file) a full read after its last edit
pays the hold. After a completed .py edit the PostToolUse response names the program to run. An error in Makoto
itself blocks, names the error and the one way to disable Makoto.

Sections, in dependency order: paths, shell, borrowed, observed, transcript, switch, provenance, evaluate, hook, checkpoint, __main__.
Excerpts from DetIO and Causality (leaves, modified; receipt, unchanged) and one design
adaptation (execution_subjects, run_output) are credited in NOTICE.
"""
import ast
import contextlib
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
from functools import lru_cache
from pathlib import Path

# Defaults; MAKOTO_STATE_DIR, MAKOTO_LOCK_SECONDS and MAKOTO_CHECKPOINT override them (see README).
# MAKOTO_ADAPTER accepts only 'inferred'; any other value is an error, and errors block.
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
        # Only a digit written flush against the operator (2>x) is a descriptor.
        flush = re.findall(r'(?:^|\s)(\d+)(?=[<>])', re.sub(r'"(?:\\.|[^"\\])*"|\'[^\']*\'', lambda q: 'x' * len(q[0]), parts[0][0]))
        words, redirects = [], []
        i = 0
        while i < len(raw):
            word = raw[i]
            if word in ('<', '>', '>>', '>|', '<<', '<<-'):
                if i + 1 >= len(raw):
                    return None
                target = shlex.split(raw[i + 1])[0]
                if words and words[-1].isdigit() and words[-1] in flush:
                    flush.remove(words.pop())  # descriptor prefix, e.g. 2>errors.txt
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
# borrowed: Excerpts from DetIO and Causality; source pins in NOTICE.
#
# Copyright 2026 Clear-Sights. Licensed under Apache-2.0, whose text is in NOTICE (LICENSE is Makoto's FSL-1.1-ALv2).
# Changes: numeric leaves.

def leaves(r, path=()):
    """DetIO core.leaves: every string in a nested native response."""
    if isinstance(r, str):
        yield path, r
    elif type(r) in (int, float):
        yield path, str(r)
    for k, v in (r.items() if isinstance(r, dict) else enumerate(r) if isinstance(r, list) else ()):
        yield from leaves(v, path + (k,))


def receipt(claim, trace, fingerprint):
    # Causality receipt, copied unchanged; no trace-free admitted write.
    if not trace:
        raise ValueError("a claim without a trace is a belief, not a receipt")
    return {"claim": claim, "trace": trace, "instruments": fingerprint}


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
                    result.extend({'subject': w, 'removed': True} for w in words[1:-1] if not w.startswith('-'))
            elif name == 'sed' and any(w.startswith('-i') for w in words[1:]):
                result.append({'subject': words[-1]})
            elif name == 'gofmt' and '-w' in words[1:]:
                result.extend({'subject': w} for w in words[1:] if w != '-w' and not w.startswith('-'))
    return list(event.get('makoto', {}).get('effects', [])) + [r for r in result if r['subject'] != '' and not any(c in r['subject'] for c in '$*?`')]


# ======================================================================
# transcript: Read host transcript history; assistant text is never a run.
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
    return {'path': path, 'session_id': session_id, 'offset': 0, 'head': '', 'events': [], 'nocwd': [],
            'first_pre': {}, 'pending': {}, 'error': None}


HEAD_BYTES = 4096


def head_digest(stream, offset):
    stream.seek(0)
    return hashlib.sha256(stream.read(min(offset, HEAD_BYTES))).hexdigest()


def parse_transcript(cache):
    """Read only the bytes after cache['offset'], complete lines only, and extend the cache."""
    with Path(cache['path']).open('rb') as stream:
        size = stream.seek(0, 2)
        if size < cache['offset'] or head_digest(stream, cache['offset']) != cache['head']:
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
        if cache['offset'] - len(line) < HEAD_BYTES:
            with Path(cache['path']).open('rb') as stream:
                cache['head'] = head_digest(stream, cache['offset'])
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
        # Missing history adds nothing and never replaces the verified journal.
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
        except (ValueError, TypeError, RecursionError):
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
    return {'subject': identity(target, event), 'display': target,
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


def shell_words(command):
    """POSIX words with shell operators split out, or None for unbalanced quoting."""
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=';&|()<>\n')
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return None


def json_loaded_paths(command):
    """Files a successful `python -c` parsed whole with json.load on a literal path.

    json.load either consumes the entire file or raises, so a call that exits
    zero read the file in full. Statements joined by `;` hide an earlier
    failure behind a later exit status, so only a lone call or an `&&` chain
    counts.
    """
    words = shell_words(command)
    if words is None:
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


def simple_argv(command):
    """No guessed branch selection or shell expansion from an aggregate output."""
    words = shell_words(command)
    if words is None:
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


def import_closure(program, cwd):
    """Python files under cwd that a run of program imports, read from disk now.

    Static: ast Import/ImportFrom nodes, resolved from the importing program's
    directory first, then cwd; packages contribute their __init__.py files.
    """
    cwd = normalized_path(cwd or os.getcwd(), '/')
    inside = lambda path: path == cwd or path.startswith(cwd.rstrip('/') + '/')
    start = normalized_path(program.removeprefix('file:'), cwd)
    if not start.endswith('.py') or not inside(start):
        return set()
    found, queue = set(), [start]
    while queue and len(found) < 500:
        path = queue.pop()
        if path in found:
            continue
        try:
            with open(path, encoding='utf-8') as handle:
                tree = ast.parse(handle.read(), path)
        except (OSError, ValueError, SyntaxError, RecursionError):
            continue
        found.add(path)
        here = posixpath.dirname(path)

        def module_files(parts, bases):
            for base in bases:
                chain, directory = [], base
                for part in parts:
                    directory = posixpath.join(directory, part)
                    chain.append(directory)
                if not parts:
                    return [posixpath.join(base, '__init__.py')] if os.path.isfile(posixpath.join(base, '__init__.py')) else []
                leaf = chain[-1]
                if os.path.isfile(leaf + '.py') or os.path.isfile(posixpath.join(leaf, '__init__.py')):
                    files = [posixpath.join(d, '__init__.py') for d in chain[:-1]]
                    files.append(leaf + '.py' if os.path.isfile(leaf + '.py') else posixpath.join(leaf, '__init__.py'))
                    return [f for f in files if os.path.isfile(f)]
            return []

        wanted = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    wanted.append(module_files(alias.name.split('.'), [here, cwd]))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = here
                    for _ in range(node.level - 1):
                        base = posixpath.dirname(base)
                    bases = [base]
                else:
                    bases = [here, cwd]
                parts = (node.module or '').split('.') if node.module else []
                wanted.append(module_files(parts, bases))
                for alias in node.names:
                    if alias.name != '*':
                        wanted.append(module_files(parts + [alias.name], bases))
        for files in wanted:
            queue.extend(f for f in files if inside(f) and f not in found)
    return {'file:' + path for path in found}


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
# provenance: Ordered sweep of the session's edits, runs and full reads.

class Ledger:
    def __init__(self):
        self.q = 0
        self.turn = '0'
        self.pending = {}
        self.pending_order = {}
        self.denied = {}
        self.seen = set()
        self.reservations = {}
        self.unknown = []
        self.code_changes = {}
        self.executions = []
        self.readbacks = []
        self.shebangs = set()
        self.compiled = {}
        self.notes = {}
        self.new_notes = []

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
                self.code_changes[subject] = dict(prior, subject=subject, display=rename['subject'])
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
            return
        spelling = next((effect['subject'] for effect in effects(event)
                         if self.subject(effect['subject'], event) == subject), subject)
        form = edited_forms(event, spelling)
        if form or subject in self.code_changes:
            prior = self.code_changes.get(subject, {})
            form = form or dict(prior)
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

    def bash_order(self, pre, post, started, no_effect):
        """Apply lexical acts inside one paired call at distinct positions."""
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
            if not no_effect:
                for effect in effects(segment):
                    subject = self.subject(effect['subject'], pre)
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
                        for paid in sorted(import_closure(subject, pre.get('cwd')) - {subject}):
                            paid_start = position if self.code_changes.get(paid, {}).get('tool_use_id') == tid else started
                            self.executions.append({'q': position, 'started': paid_start,
                                                    'subjects': {paid}, 'tool_use_id': tid})
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

    def ingest(self, event, admitted=True):
        self.q += 1
        self.new_notes = []
        name, meta = event['hook_event_name'], event.get('makoto', {})
        if meta.get('turn_id') is not None:
            self.turn = str(meta['turn_id'])
        elif name == 'UserPromptSubmit' and not meta.get('same_turn'):
            self.turn = str(self.q)
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
            return
        if name not in ('PostToolUse', 'PostToolUseFailure'):
            return
        tid = event.get('tool_use_id')
        pre = self.pending.get(tid)
        if pre is None and tid in self.denied and tid not in self.seen:
            denied = self.denied[tid]
            if (event.get('tool_name', denied.get('tool_name')) == denied.get('tool_name')
                    and ('tool_input' not in event or event['tool_input'] == denied.get('tool_input', {}))
                    and meta.get('no_effect') is not True and not refused(event)):
                # A host-reported completion after denial cannot pay a hold,
                # but its mutation still counts as an edit.
                for effect in effects(denied) + effects(event):
                    subject = self.subject(effect['subject'], denied)
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
                self.change_code(pre, subject)
                if (pre.get('tool_name') in ('Write', 'Edit', 'MultiEdit') and not failed(event) and subject.endswith('.py')
                        and subject.startswith('file:') and (pre.get('cwd') or event.get('cwd'))):
                    cwd = normalized_path(pre.get('cwd') or event.get('cwd'), '/').rstrip('/')
                    noted = self.notes.get(subject)
                    if subject[5:].startswith(cwd + '/') and (noted is None or any(
                            run['started'] > noted and subject in run['subjects'] for run in self.executions)):
                        self.notes[subject] = self.q
                        self.new_notes.append(subject)
        if not failed(event) or no_effect:
            self.reservations.pop(tid, None)
        # Paired call plus returned response proves the act, even on failure.
        # Resolve the invocation against its recorded cwd, never final prose.
        if run_output(event) and (not ordered or pre.get('makoto', {}).get('invocation') or meta.get('invocation')):
            invoked = execution_subjects(pre, self.code_changes, event)
            if invoked:
                self.executions.append({'q': self.q, 'started': started,
                                        'subjects': invoked, 'tool_use_id': tid})
                for subject in sorted(invoked):
                    for paid in sorted(import_closure(subject, pre.get('cwd')) - invoked):
                        paid_start = self.q if self.code_changes.get(paid, {}).get('tool_use_id') == tid else started
                        self.executions.append({'q': self.q, 'started': paid_start,
                                                'subjects': {paid}, 'tool_use_id': tid})
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


# ======================================================================
# evaluate: Rule d at a final answer, derived only from literal session observations.

def evaluate(ledger, event):
    """Rule d findings and their receipts: a code file edited by this agent and not run since."""
    findings, snapshot = [], []
    if event['hook_event_name'] not in FINAL:
        return findings, snapshot
    # A final answers for what its own agent wrote: a subagent's Stop is not held for a sibling worker's file.
    for change in ledger.changed_code().values():
        if change.get('agent') != event.get('agent_id'):
            continue
        runs = ledger.run_witnesses(change)
        readbacks = ledger.readback_witnesses(change)
        if not runs and not readbacks:
            findings.append({'rule': 'd', 'family': 'd', 'shape': 'switch',
                             'subject': change['display'],
                             'missing': UNCHANGED + ' Missing: a run of it, with its output read, after its last edit. Clear: Run it and read its output.'})
        else:
            witnesses = runs or readbacks
            snapshot.append(receipt(change['display'], [run['tool_use_id'] for run in witnesses],
                                    'makoto2.switch/execution-v1' if runs else 'makoto2.switch/readback-v1'))
    return list({(f['rule'], f['subject']): f for f in findings}.values()), snapshot


# ======================================================================
# hook: Locked append-only hook journal and fail-closed admission transport.

UNCHANGED = 'Unchanged: Do not assume what can change has not.'


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
    if 'last_assistant_message' in event and not isinstance(event['last_assistant_message'], str):
        raise ValueError('last_assistant_message must be text')
    if event['hook_event_name'] in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure') and (not isinstance(event.get('tool_use_id'), str) or not event['tool_use_id']):
        raise ValueError('tool events require an exact tool_use_id')
    return event


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
            cache['rows'].append({'event': row['event'], 'admitted': row['admitted'], 'sha256': seal})
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

CHECKPOINT_VERSION = 2


def quarantine(path):
    """Move a corrupted journal (and its derived checkpoint) aside; a fresh journal starts at `path`."""
    if path.exists():
        os.replace(path, path.with_name(path.name + '.corrupt-%d' % time.time_ns()))
    with contextlib.suppress(OSError):
        os.remove(str(path) + '.ckpt')


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


DISABLE = 'claude plugin disable makoto'


def infrastructure_block(raw, error):
    """Block in the shape the host reads for this event; name the error and the one way out."""
    try:
        event = json.loads(raw)
    except ValueError:
        event = {}
    event = event if isinstance(event, dict) else {}
    if event.get('hook_event_name') == 'UserPromptSubmit':
        return {}  # the user's own prompt is not a step Makoto governs
    reason = ('makoto infrastructure error, step blocked: %s: %s. To disable Makoto run in a terminal: %s'
              % (type(error).__name__, error, DISABLE))
    return d_out(event, reason)


def run_note(ledger, event):
    """One note per edited .py file until a run pays it; guidance, never a hold."""
    if event.get('hook_event_name') != 'PostToolUse' or not ledger.new_notes or not event.get('cwd'):
        return {}
    cwd = normalized_path(event['cwd'], '/').rstrip('/')
    files = []
    for top, dirs, names in os.walk(cwd):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d != '__pycache__')
        files.extend(posixpath.join(top, n) for n in sorted(names) if n.endswith('.py'))
        if len(files) > 2000:
            break
    closures = {f: import_closure(f, cwd) for f in files}
    imported = set()
    for f, closure in closures.items():
        imported |= closure - {'file:' + f}
    edited = ledger.new_notes[0]
    shown = edited[5:][len(cwd) + 1:]
    tops = sorted((f[len(cwd) + 1:] for f in files if 'file:' + f not in imported and edited in closures[f]),
                  key=lambda r: (len(r), r))
    return {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext':
            'Before your final answer, run python3 ' + (tops[0] if tops else shown) + ' and read its output: it runs ' + shown + '.'}}


def d_out(event, reason):
    if not reason:
        return {}
    if event.get('hook_event_name') == 'PreToolUse':
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': reason}}
    return {'decision': 'block', 'reason': reason}


def replay(records, base):
    """The Ledger after `records`, starting from a checkpointed (count, marshalled state) when given."""
    start, state = base
    # D20: a record that cannot be ingested is unknown, never partial,
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
            try:
                journal = sigma_read(path, event['session_id'], state['journal'] if state else None)
            except (ValueError, KeyError, TypeError):
                # Corrupted journal: keep it beside the fresh one and decide from what can still be read
                # (the transcript), so only an edit whose run is really missing is held.
                quarantine(path)
                state = checkpoint_load(path, event['session_id']) if checkpoint else None
                journal = sigma_read(path, event['session_id'], state['journal'] if state else None)
            records, transcript = history(event, journal, state['transcript'] if state else None)
            tags = [(tag, admitted) for _, admitted, tag in records]
            base = (0, None)
            # Rows without their own cwd took this candidate's: a new cwd replays in full.
            if (state and state['ledger'] is not None and state.get('cwd') == event.get('cwd', '')
                    and tags[:len(state['tags'])] == state['tags']):
                base = (len(state['tags']), state['ledger'])
            ledger = replay(records, base)
            if state:
                state['transcript'], state['cwd'] = transcript, event.get('cwd', '')
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
            try:
                findings, snapshot = evaluate(ledger, event)
            except (KeyError, TypeError, ValueError) as error:
                contract = str(error)
            reason = None
            if contract:
                reason = 'makoto contract: ' + contract
            elif findings:
                reason = '; '.join('makoto rule ' + f['rule'] + ' [' + f['shape'] + ']: ' + json.dumps(f['subject'], ensure_ascii=False) + ': ' + f['missing'] for f in findings)
            row = {'event': event, 'admitted': not bool(reason), 'adapter': adapter,
                   'findings': findings, 'contract_error': contract, 'snapshot': snapshot,
                   'turn_id': ledger.turn, 'unknown': ledger.unknown}
            # Validate transitions before persisting invalid host records.
            ledger.ingest(event, row['admitted'])
            sigma_append(path, row, journal[-1]['sha256'] if journal else '')
            if state:
                checkpoint_save(path, saved)
            if reason:
                return d_out(event, reason)
            try:
                return run_note(ledger, event)
            except Exception:
                return {}
    except Exception as error:
        # Fail closed: an error in Makoto's own work (state, lock, journal, transcript,
        # malformed host event) blocks, names the error and says how to disable Makoto.
        return infrastructure_block(raw, error)


# ======================================================================
# __main__: Live entry: python -m makoto2, one serialized native event on stdin.

def run():
    raw = ''
    try:
        raw = sys.stdin.read()
        cfg = dict(CONFIG)
        cfg['state_dir'] = os.path.expanduser(os.environ.get('MAKOTO_STATE_DIR', cfg['state_dir']))
        cfg['adapter'] = os.environ.get('MAKOTO_ADAPTER', cfg['adapter'])
        cfg['lock_seconds'] = float(os.environ.get('MAKOTO_LOCK_SECONDS', cfg['lock_seconds']))
        cfg['checkpoint'] = os.environ.get('MAKOTO_CHECKPOINT', '1') != '0'
        response = main(raw, cfg)
    except Exception as error:
        response = infrastructure_block(raw, error)
    sys.stdout.write(json.dumps(response))
    return 0


if __name__ == '__main__':
    sys.exit(run())
