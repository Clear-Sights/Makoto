"""Commit scope from recorded git arguments and successful staging receipts.

Never invokes git or assumes all session edits belong to a commit.
"""
import fnmatch
import json
import re

from .observed import failed, programs, response_text
from .paths import normalized_path, program_name
from .shell import selected_segments


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
