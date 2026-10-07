"""Lexical native tool adapters; no subject-specific vocabulary or execution."""
import hashlib
import json
import os
import re
import shlex
from .borrowed import leaves
from .shell import ordered_segments, redirected_argv
from .paths import normalized_path, program_name

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
        if words:
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
    return event['hook_event_name'] == 'PostToolUseFailure' or isinstance(response, dict) and bool(response.get('is_error') or response.get('isError') or any(response.get(k) not in (None, 0, '0', '') for k in ('exitCode', 'exit_code', 'exit')))


def effects(event):
    result = list(event.get('makoto', {}).get('effects', []))
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
            elif name in ('touch', 'rm', 'mkdir', 'rmdir', 'truncate', 'tee'):
                result.extend({'subject': w} for w in words[1:] if not w.startswith('-'))
            elif name in ('cp', 'mv') and len(words) > 2:
                result.append({'subject': words[-1]})
                if name == 'mv':
                    result.append({'subject': words[-2], 'removed': True})
            elif name == 'sed' and any(w.startswith('-i') for w in words[1:]):
                result.append({'subject': words[-1]})
            elif name == 'gofmt' and '-w' in words[1:]:
                result.extend({'subject': w} for w in words[1:] if w != '-w' and not w.startswith('-'))
    return result


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
                result.extend(w for w in words[1:] if not w.startswith('-'))
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
                result.extend(w for w in words[1:] if not w.startswith('-'))
            elif (program_name(words[0]) in ('pip', 'pip3', 'npm', 'pnpm', 'yarn', 'cargo', 'go') and any(w in ('install', 'add', 'get', 'view') for w in words[1:])) or program_name(words[0]) == 'git' and any(w in ('fetch', 'clone', 'pull') for w in words[1:]):
                result.extend(words[1:])
    result.extend(pre.get('makoto', {}).get('network_subjects', []))
    return result
