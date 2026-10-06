"""Native settled evidence adapters. No filesystem probes or prose semantics."""
import hashlib
import json
import os
import re
import shlex

WRITERS = {'Write', 'Edit', 'MultiEdit', 'NotebookEdit'}
FINAL = {'Stop', 'SubagentStop', 'PreDelivery'}


def digest(value):
    data = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data.encode()).hexdigest()


def identity(value, event):
    if isinstance(value, dict):
        # Typed identities are host-owned; do not flatten authority/namespace.
        return json.dumps(value, sort_keys=True, separators=(',', ':'))
    if not isinstance(value, str) or not value:
        raise ValueError('subject identity must be nonempty')
    if value.startswith(('https://', 'http://', 'id:', 'git:', 'command:')):
        return value
    if value.startswith('file:'):
        value = value[5:]
    # Lexical canonical path: verified symlink aliases require host mappings.
    return 'file:' + os.path.normpath(os.path.abspath(os.path.join(event.get('cwd') or os.getcwd(), value)))


def command(event):
    return event.get('tool_input', {}).get('command', '')


def argv(event):
    try:
        return shlex.split(command(event))
    except ValueError:
        return []


def git_action(event):
    # Shell punctuation establishes command boundaries; comments cannot hide
    # a git call behind a leading basis declaration. No prose classification.
    try:
        lexer = shlex.shlex(command(event), posix=True, punctuation_chars=';&|()\n')
        lexer.whitespace = ' \t\r'
        lexer.whitespace_split = True
        segments, current = [], []
        for word in lexer:
            if word and all(c in ';&|()\n' for c in word):
                segments.append(current)
                current = []
            else:
                current.append(word)
        segments.append(current)
    except ValueError:
        return False
    for words in segments:
        if not words or words[0] != 'git':
            continue
        i = 1
        while i < len(words) and words[i].startswith('-'):
            i += 2 if words[i] in ('-C', '-c', '--git-dir', '--work-tree') else 1
        if i < len(words) and words[i] in ('commit', 'push'):
            return True
    return False


def dependent(event):
    name = event['hook_event_name']
    if name in FINAL:
        return bool(event.get('last_assistant_message')) or bool(event.get('makoto', {}).get('obligations')) or bool(event.get('makoto', {}).get('dependencies'))
    return name == 'PreToolUse' and (event.get('tool_name') in WRITERS or
           (event.get('tool_name') == 'Bash' and git_action(event)) or
           bool(event.get('makoto', {}).get('dependencies')) or
           bool(event.get('makoto', {}).get('obligations')))


def text_of(event):
    if event['hook_event_name'] in FINAL:
        return event.get('last_assistant_message', '')
    ti = event.get('tool_input', {})
    keys = ('content', 'new_string', 'old_string', 'edits', 'cells', 'new_source', 'command')
    return '\n'.join(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                     for k in keys if (v := ti.get(k)) is not None)


def effects(event):
    result = list(event.get('makoto', {}).get('effects', []))
    if event.get('tool_name') in WRITERS:
        ti = event.get('tool_input', {})
        target = ti.get('file_path') or ti.get('notebook_path')
        if target:
            result.append({'subject': target})
    return result


def response_text(response):
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        if 'stdout' in response or 'stderr' in response:
            return str(response.get('stdout', '')) + '\n' + str(response.get('stderr', ''))
        if isinstance(response.get('file'), dict):
            return response['file'].get('content', '')
        for key in ('content', 'stdout', 'output'):
            if key in response:
                value = response[key]
                return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return json.dumps(response, ensure_ascii=False)


def failed(event):
    response = event.get('tool_response', {})
    return event['hook_event_name'] == 'PostToolUseFailure' or (isinstance(response, dict) and
            bool(response.get('is_error') or response.get('isError')))


def completed(event):
    response = event.get('tool_response')
    if response is None or (isinstance(response, dict) and response.get('backgroundTaskId')):
        return False
    if event.get('tool_name') == 'Bash':
        return isinstance(response, dict) and any(type(response.get(k)) is int for k in ('exitCode', 'exit_code', 'exit'))
    return not failed(event)


def native_reads(pre, post):
    ti = pre.get('tool_input', {})
    name = pre.get('tool_name')
    response = post.get('tool_response', {})
    if failed(post) or (isinstance(response, dict) and (response.get('truncated') or response.get('is_truncated'))):
        return []
    has_content = isinstance(response, str) or (isinstance(response, dict) and ('content' in response or isinstance(response.get('file'), dict) and 'content' in response['file']))
    if name == 'Read' and ti.get('file_path') and has_content:
        selector = 'content' if not any(k in ti for k in ('offset', 'limit')) else 'region:' + json.dumps([ti.get('offset'), ti.get('limit')])
        return [{'subject': ti['file_path'], 'selector': selector, 'complete': True}]
    if name == 'WebFetch' and ti.get('url') and has_content:
        return [{'subject': ti['url'], 'selector': 'representation:' + ti.get('prompt', ''), 'complete': True}]
    if name == 'Grep':
        subject = ti.get('path') or pre.get('cwd') or os.getcwd()
        return [{'subject': subject, 'selector': 'query:' + json.dumps(ti, sort_keys=True), 'complete': True}]
    words = argv(pre)
    if name == 'Bash' and len(words) in (2, 3) and words[0] == 'cat' and (len(words) == 2 or words[1] == '--') and not any(c in command(pre) for c in '|;&<>`$\n'):
        response = post.get('tool_response', {})
        if next((response[k] for k in ('exitCode', 'exit_code', 'exit') if k in response), None) == 0:
            return [{'subject': words[-1], 'selector': 'content', 'complete': True}]
    return []


# Structural trace values, never vocabulary/meaning classification.
VALUE = re.compile(r'https?://[^\s<>"\x27,;]+|(?<![\w/])(?:[\w.~-]+/|\.?\.?/|/)[^\s<>"\x27,;]+|\b[a-fA-F0-9]{7,64}\b|\b\d{3,}(?:\.\d+)?\b|\bid:[\w.:-]+')


def values(text):
    return set(VALUE.findall(text))
