"""Makoto: holds a final answer while a code or config file changed this session has not been checked since.

Live entry: cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m makoto2 (hooks/hooks.json): one native Claude Code hook event
on stdin, one JSON response on stdout. Hooks: SessionStart, UserPromptSubmit, PostToolUse, PostToolUseFailure, Stop,
SubagentStop.

What changed is read from the file system, never from edits: the first SessionStart or UserPromptSubmit records
path, size and modified time of the files under the cwd; at a final answer a file is changed when it is new or
differs. Git is optional (used only to skip ignored files). Code in any language (by extension or shebang) and
config or data files are held; plain docs never. A completed program or test run that started after the file's
modified time and succeeded (no failed call, no error marker in its output) pays it when it names the file, a program or test in the same top-level folder, or is a project-wide
runner; a config or data file is also paid by a full read after its modified time. A Stop with stop_hook_active is
admitted. After a completed Write, Edit, MultiEdit or NotebookEdit of a code file the PostToolUse response names
what to run, once per file until paid. An error in Makoto blocks a final answer or tool step, names the error and
the one way to disable Makoto. State: one JSON file per session under a lock in MAKOTO_STATE_DIR.
"""
import contextlib
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

STATE_DIR = '~/.claude/makoto2_state'
LOCK_SECONDS = 3.0
MAX_FILES = 20000
DISABLE = 'claude plugin disable makoto'
UNCHANGED = 'Unchanged: Do not assume what can change has not.'
MISSING = ' Missing: a run of it, with its output read, after its last edit. Clear: Run it and read its output.'
FAILED = ' Missing: a run of it that succeeds, after its last edit. Clear: Fix the error, run it again and read its output.'
NOTE = 'Before your final answer, run the program or tests that use %s and read the output.'
FINAL = ('Stop', 'SubagentStop')
HANDLED = FINAL + ('PostToolUse', 'PostToolUseFailure', 'SessionStart', 'UserPromptSubmit')
EDITORS = ('Write', 'Edit', 'MultiEdit', 'NotebookEdit')

CODE = frozenset('py pyw js jsx mjs cjs ts tsx sh bash zsh fish rb pl php lua r rs go c h cc cpp hpp java kt swift '
                 'scala cs fs ex exs erl clj sql ps1 bat cmd ipynb tcl awk dart zig nim jl hs ml vue svelte'.split())
CONFIG = frozenset('json jsonc yaml yml toml ini cfg conf config xml properties env csv tsv'.split())
CONFIG_NAMES = frozenset(('Makefile', 'Dockerfile', 'Rakefile', 'Gemfile', 'Procfile', '.env'))
SKIP_DIRS = frozenset(('.git', 'node_modules', '__pycache__', '.venv', 'venv'))  # other build output: only when git ignores it

RUNTIMES = re.compile(r'(?:python[\d.]*|pypy\d*|node|nodejs|deno|bun|ruby|perl|php|lua|Rscript|java|javac|dotnet|make|'
                      r'gmake|npx|pytest|py\.test|jest|vitest|mocha|sh|bash|zsh|fish|pwsh|tclsh[\d.]*)\Z')
SUBCOMMANDS = {'go': ('run', 'test', 'build'), 'cargo': ('run', 'test'), 'npm': ('run', 'test', 'start', 'run-script'),
               'yarn': ('run', 'test', 'start'), 'pnpm': ('run', 'test', 'start')}
WIDE = re.compile(r'(?:make|gmake|npx|pytest|py\.test|jest|vitest|mocha|npm|yarn|pnpm)\Z')  # project-wide runners
WRAPPERS = frozenset('time nohup exec sudo command env stdbuf nice'.split())
PRINTERS = frozenset('cat bat less more nl tac'.split())
SEPARATORS = frozenset(('&&', '||', ';', '|', '|&', '&', '(', ')', ';;', '{', '}'))
ERROR = re.compile(r'Traceback \(most recent call last\)|^[\w.]+(?:Error|Exception):|\bexit(?:=|\s+code\s+)0*[1-9]|'
                   r'\bFAILED\b|panic:|command not found|No such file or directory', re.M)
HEREDOC = re.compile(r'<<-?\s*([\'"]?)(\w+)\1[^\n]*\n.*?\n[ \t]*\2[ \t]*(?=\n|$)', re.S)


# ---------------------------------------------------------------- shell

def segments(command):
    """Split a command into (argv, redirect targets) in order; static text only, never evaluated."""
    command = HEREDOC.sub(lambda m: m.group(0).split('\n', 1)[0], command).replace('\n', ' ; ')
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    result, argv, targets, i = [], [], [], 0
    while i < len(tokens):
        token = tokens[i]
        if token in SEPARATORS:
            if argv or targets:
                result.append((argv, targets))
            argv, targets = [], []
        elif token.startswith(('>', '&>')):
            if token in ('>', '>>', '>|', '&>') and i + 1 < len(tokens):
                targets.append(tokens[i + 1])
                i += 1
            elif token.startswith('>&') and len(token) == 2:
                i += 1  # 2>&1: a descriptor, not a file
        elif token.startswith('<'):
            i += token in ('<', '<<', '<<<')
        elif not (token.isdigit() and i + 1 < len(tokens) and tokens[i + 1].startswith('>')):
            argv.append(token)
        i += 1
    if argv or targets:
        result.append((argv, targets))
    return result


def strip_wrappers(argv):
    while argv and (re.fullmatch(r'\w+=.*', argv[0]) or os.path.basename(argv[0]) in WRAPPERS
                    or argv[0] == 'timeout' and len(argv) > 1):
        if argv[0] == 'timeout':
            argv = argv[2:] if len(argv) > 2 else []
        else:
            argv = argv[1:]
    return argv


def is_run(argv):
    if not argv:
        return False
    name = os.path.basename(argv[0])
    if name in SUBCOMMANDS:
        return len(argv) > 1 and argv[1] in SUBCOMMANDS[name]
    if RUNTIMES.match(name) and not (name.startswith('python') and argv[1:2] == ['-m'] and argv[2:3] in (['pip'], ['venv'])):
        return not any(a in ('--version', '-V', '--help', '-h') for a in argv[1:2])
    return argv[0].startswith(('./', '../', '/')) and '/' in argv[0] and name not in PRINTERS


def kind(path):
    """'code', 'config' or None for a plain doc or anything else."""
    name = os.path.basename(path)
    suffix = name.rpartition('.')[2].lower() if '.' in name.strip('.') else ''
    if suffix in CODE:
        return 'code'
    if suffix in CONFIG or name in CONFIG_NAMES:
        return 'config'
    if not suffix:
        try:
            with open(path, 'rb') as stream:
                return 'code' if stream.read(2) == b'#!' else None
        except OSError:
            return None
    return None



def is_wide(argv):
    name = os.path.basename(argv[0])
    if name in SUBCOMMANDS:
        return argv[1] in ('test', 'run', 'start', 'run-script') and name != 'go' or name == 'go' and argv[1] == 'test'
    if name.startswith('python'):
        return argv[1:2] == ['-m'] and argv[2:3] in (['pytest'], ['unittest'], ['tox'])
    return bool(WIDE.match(name))


# ---------------------------------------------------------------- files

def absolute(path, cwd):
    path = os.path.expanduser(path)
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(cwd, path))


def top(rel):
    return rel.split('/')[0] if '/' in rel else ''


def listing(root):
    """{relative path: [size, mtime_ns]} of the files under root, at most MAX_FILES."""
    names = None
    if os.path.exists(os.path.join(root, '.git')):  # git only skips ignored files
        try:
            out = subprocess.run(['git', '-C', root, 'ls-files', '-co', '--exclude-standard', '-z'],
                                 capture_output=True, timeout=5, check=True).stdout.decode('utf-8', 'replace')
            names = [n for n in out.split('\0') if n and not set(n.split('/')[:-1]) & SKIP_DIRS]
        except (OSError, subprocess.SubprocessError):
            names = None
    if names is None:
        names = []
        for here, dirs, found in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            names.extend(os.path.relpath(os.path.join(here, f), root).replace(os.sep, '/') for f in found)
            if len(names) > MAX_FILES:
                break
    result = {}
    for name in names[:MAX_FILES]:
        try:
            info = os.stat(os.path.join(root, name))
        except OSError:
            continue
        result[name] = [info.st_size, info.st_mtime_ns]
    return result


# ---------------------------------------------------------------- state

@contextlib.contextmanager
def locked(path, wait):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    deadline = time.monotonic() + wait
    with open(path + '.lock', 'a+b') as stream:
        while True:
            try:
                if fcntl:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError('state lock busy')
                time.sleep(0.02)
        yield


def load(path):
    try:
        with open(path, encoding='utf-8') as stream:
            state = json.load(stream)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save(path, state):
    temporary = path + '.tmp%d' % os.getpid()
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(state, stream)
    os.replace(temporary, path)


# ---------------------------------------------------------------- rule

def run_record(argv, cwd, root):
    """What a completed run names, as paths under root: files, directories ('/'-ended) and module files."""
    named = set()
    for word in argv:
        candidates = [word]
        if re.fullmatch(r'[\w.]+', word) and '/' not in word:
            candidates.append(word.replace('.', '/') + '.py')
        for candidate in candidates:
            path = absolute(candidate, cwd)
            if path == root or path.startswith(root + os.sep):
                rel = os.path.relpath(path, root).replace(os.sep, '/')
                if os.path.isdir(path):
                    named.add('/' if rel == '.' else rel + '/')
                elif os.path.isfile(path) and kind(path):
                    named.add(rel)
    return {'wide': is_wide(argv), 'named': sorted(named)}


def reaches(run, rel):
    if run['wide']:
        return True
    for name in run['named']:
        if name == rel or name.endswith('/') and (name == '/' or rel.startswith(name)) \
                or not name.endswith('/') and top(name) == top(rel):
            return True
    return False


def paid(state, rel, mtime):
    what = kind(os.path.join(state['root'], rel))
    if any(r['t'] > mtime and r.get('ok', True) and reaches(r, rel) for r in state['runs']):
        return True
    return what == 'config' and any(r['t'] > mtime and r['path'] == rel for r in state['reads'])


def failed(event):
    """A tool call that failed, or whose stdout or stderr holds an error marker."""
    out = event.get('tool_response')
    out = '\n'.join(str(out.get(k) or '') for k in ('stdout', 'stderr')) if isinstance(out, dict) else str(out or '')
    return event.get('hook_event_name') == 'PostToolUseFailure' or bool(ERROR.search(out))


def record(state, event):
    """Note completed runs and full reads; return the files newly needing a note."""
    root, tool, given = state['root'], event.get('tool_name'), event.get('tool_input') or {}
    cwd, now, fresh = event.get('cwd') or root, time.time(), []
    if event.get('hook_event_name') == 'PostToolUseFailure' and tool != 'Bash':
        return fresh
    began, state['last'] = state.get('last', now), now  # a run began after the previous hook event, so a change it made is newer
    if tool == 'Read' and isinstance(given.get('file_path'), str) and not given.get('offset') and not given.get('limit'):
        state['reads'] = (state['reads'] + [{'t': now, 'path': os.path.relpath(absolute(given['file_path'], cwd), root).replace(os.sep, '/')}])[-300:]
    elif tool == 'Bash' and isinstance(given.get('command'), str):
        for argv, _ in segments(given['command']):
            argv = strip_wrappers(argv)
            if argv and argv[0] == 'cd':
                cwd = absolute(argv[1], cwd) if len(argv) > 1 else os.path.expanduser('~')
            elif argv and os.path.basename(argv[0]) in PRINTERS:
                for word in argv[1:]:
                    if not word.startswith('-'):
                        state['reads'] = (state['reads'] + [{'t': now, 'path': os.path.relpath(absolute(word, cwd), root).replace(os.sep, '/')}])[-300:]
            elif is_run(argv):
                state['runs'] = (state['runs'] + [dict(run_record(argv, cwd, root), t=began, ok=not failed(event))])[-300:]
    elif tool in EDITORS:
        target = given.get('file_path') or given.get('notebook_path')
        if isinstance(target, str) and target:
            rel = os.path.relpath(absolute(target, cwd), root).replace(os.sep, '/')
            if kind(absolute(target, cwd)) == 'code' and rel not in state['noted']:
                state['noted'].append(rel)
                fresh.append(rel)
    # a note stays quiet only until a run reaches its file
    for rel in list(state['noted']):
        try:
            changed = os.stat(os.path.join(root, rel)).st_mtime
        except OSError:
            continue
        if rel not in fresh and paid(state, rel, changed):
            state['noted'].remove(rel)
    return fresh


def unpaid(state):
    now, snapshot, held = listing(state['root']), state['snapshot'], []
    for rel in sorted(now):
        if snapshot.get(rel) == now[rel] or not kind(os.path.join(state['root'], rel)):
            continue
        mtime = now[rel][1] / 1e9
        if not paid(state, rel, mtime):  # a failed run after the last edit changes the text
            held.append((rel, any(r['t'] > mtime and reaches(r, rel) for r in state['runs'])))
    return held


def respond(event, config):
    name = event.get('hook_event_name')
    if name not in HANDLED:
        return {}
    if not isinstance(event.get('session_id'), str) or not event['session_id']:
        raise ValueError('missing session identity')
    path = os.path.join(config['state_dir'], hashlib.sha256(event['session_id'].encode()).hexdigest() + '.json')
    with locked(path, config['lock_seconds']):
        state = load(path)
        if name in ('SessionStart', 'UserPromptSubmit'):
            if 'snapshot' not in state:
                root = event.get('cwd') or os.getcwd()
                state = {'root': root, 'snapshot': listing(root), 'runs': [], 'reads': [], 'noted': [], 'unpaid': []}
            state['last'] = time.time()
            save(path, state)
            return {}
        if 'snapshot' not in state:
            return {}
        if name in FINAL:
            held = unpaid(state)
            if event.get('stop_hook_active') or not held:
                state['unpaid'] = [f for f, _ in held]
                save(path, state)
                return {}
            reason = '; '.join('makoto rule d [switch]: ' + json.dumps(f, ensure_ascii=False) + ': ' + UNCHANGED + (FAILED if bad else MISSING)
                               for f, bad in held)
            return {'decision': 'block', 'reason': reason}
        fresh = record(state, event)
        save(path, state)
    if fresh:
        text = '\n'.join(NOTE % os.path.relpath(os.path.join(state['root'], p), event.get('cwd') or state['root']) for p in fresh)
        return {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': text}}
    return {}


def infrastructure_block(event, error):
    if not isinstance(event, dict) or event.get('hook_event_name') not in FINAL + ('PostToolUse', 'PostToolUseFailure', None):
        return {}  # never block the user's own prompt or session start
    reason = ('makoto infrastructure error, step blocked: %s: %s. To disable Makoto run in a terminal: %s'
              % (type(error).__name__, error, DISABLE))
    return {'decision': 'block', 'reason': reason}


def main(raw, config):
    event = {}
    try:
        event = json.loads(raw)
        if not isinstance(event, dict) or not isinstance(event.get('hook_event_name'), str):
            raise ValueError('missing hook event')
        return respond(event, config)
    except Exception as error:
        return infrastructure_block(event, error)


def run():
    raw = ''
    try:
        raw = sys.stdin.read()
        config = {'state_dir': os.path.expanduser(os.environ.get('MAKOTO_STATE_DIR', STATE_DIR)),
                  'lock_seconds': float(os.environ.get('MAKOTO_LOCK_SECONDS', LOCK_SECONDS))}
        response = main(raw, config)
    except Exception as error:
        response = infrastructure_block({}, error)
    sys.stdout.write(json.dumps(response))
    return 0


if __name__ == '__main__':
    sys.exit(run())
