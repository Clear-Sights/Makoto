"""Makoto: holds a final answer while a file changed this session, or a file that uses it, has not been run since.

Live entry: cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m makoto2 (hooks/hooks.json): one native Claude Code hook event
on stdin, one JSON response on stdout. Hooks: SessionStart, UserPromptSubmit, PostToolUse, PostToolUseFailure, Stop,
SubagentStop.

State per session (one JSON file under a lock in MAKOTO_STATE_DIR): the snapshot of the files under the cwd taken at
SessionStart, and the lookup of which file uses which, read from import-style lines (import, from, require, include,
use, source, load) that name another file's module path or base name; changed files are read again each time.
Sets, computed without a test of their size (see sets):
  changed   = files that differ from the snapshot;
  demanded  = changed plus every file that uses them, through the lookup, among files in the lookup or with a shebang;
  checked   = demanded files reached by a successful run that began after their last change (the latest change among
              them and what they use). A run reaches the program it names plus what that uses; a test runner with
              no program argument reaches every file.
One message names demanded minus checked and the entry programs (used by no file) that reach it: a note after an
edit, once per file until checked; a hold at Stop or SubagentStop, once (stop_hook_active admits). An error in
Makoto blocks a final answer or tool step, names the error and the one way to disable Makoto.
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
MAX_READ = 262144
DISABLE = 'claude plugin disable makoto'
MESSAGE = 'Not run since a change: %s. Run %s and read the output.'
FINAL = ('Stop', 'SubagentStop')
HANDLED = FINAL + ('PostToolUse', 'PostToolUseFailure', 'SessionStart', 'UserPromptSubmit')
EDITORS = ('Write', 'Edit', 'MultiEdit', 'NotebookEdit')
SKIP_DIRS = frozenset(('.git', 'node_modules', '__pycache__', '.venv', 'venv'))  # other build output: only when git ignores it

RUNTIMES = re.compile(r'(?:python[\d.]*|pypy\d*|node|nodejs|deno|bun|ruby|perl|php|lua|Rscript|java|dotnet|make|gmake|'
                      r'pytest|py\.test|jest|vitest|mocha|tox|sh|bash|zsh|fish|pwsh|tclsh[\d.]*)\Z')
TESTERS = re.compile(r'(?:make|gmake|pytest|py\.test|jest|vitest|mocha|tox|rspec|phpunit|ctest)\Z')
SUBCOMMANDS = {'go': ('run', 'test'), 'cargo': ('run', 'test'), 'npm': ('run', 'test', 'start'),
               'yarn': ('run', 'test', 'start'), 'pnpm': ('run', 'test', 'start')}
WRAPPERS = frozenset('time nohup exec sudo command env stdbuf nice npx'.split())
SEPARATORS = frozenset(('&&', '||', ';', '|', '|&', '&', '(', ')', ';;', '{', '}'))
ERROR = re.compile(r'Traceback \(most recent call last\)|^[\w.]+(?:Error|Exception):|\bexit(?:=|\s+code\s+)0*[1-9]|'
                   r'\bFAILED\b|panic:|command not found|No such file or directory', re.M)
HEREDOC = re.compile(r'<<-?\s*([\'"]?)(\w+)\1[^\n]*\n.*?\n[ \t]*\2[ \t]*(?=\n|$)', re.S)
KEYWORDS = r'(?:import|from|use|include(?:_once)?|require(?:_once|_relative)?|source|load)'
IMPORT = re.compile(r'^[ \t]*#?[ \t]*' + KEYWORDS + r'\b(.*)|\b' + KEYWORDS + r'\b[ \t]*\(?[ \t]*([\'"][^\'"\n]+[\'"])', re.M)
TOKEN = re.compile(r'[\w@\-]+(?:[./][\w\-]+)*')
NOISE = frozenset(('import', 'as', 'from', 'static', 'crate', 'self', 'super', 'type'))


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
        return argv[1:2] != [] and argv[1] in SUBCOMMANDS[name]
    if RUNTIMES.match(name) and not (name.startswith('python') and argv[1:3] in (['-m', 'pip'], ['-m', 'venv'])):
        return not any(a in ('--version', '-V', '--help', '-h') for a in argv[1:2])
    return argv[0].startswith(('./', '../', '/')) and '/' in argv[0]


def is_tester(argv):
    name = os.path.basename(argv[0])
    if name in SUBCOMMANDS:
        return argv[1:2] == ['test']
    if name.startswith('python'):
        return argv[1:3] in (['-m', 'pytest'], ['-m', 'unittest'], ['-m', 'tox'])
    return bool(TESTERS.match(name))


def absolute(path, cwd):
    path = os.path.expanduser(path)
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(cwd, path))


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


# ---------------------------------------------------------------- lookup and sets

def scan(path):
    """[has a shebang, the names its import-style lines give] of one file."""
    try:
        with open(path, 'rb') as stream:
            data = stream.read(MAX_READ)
    except OSError:
        return [False, []]
    if b'\0' in data[:1024]:
        return [False, []]
    text = data.decode('utf-8', 'replace')
    names = [t for m in IMPORT.finditer(text) for t in TOKEN.findall(m.group(1) or m.group(2)) if t not in NOISE]
    return [text.startswith('#!'), list(dict.fromkeys(names))[:200]]


def close(seeds, edges):
    """The seeds and everything reached from them along edges."""
    order, seen = list(seeds), set(seeds)
    for item in order:
        for other in edges.get(item, ()):
            if other not in seen:
                seen.add(other)
                order.append(other)
    return seen


def lookup(state, files):
    """(uses, users, nodes): which file uses which, and the files in the lookup or with a shebang."""
    root, snapshot, stored = state['root'], state['snapshot'], state['scan']
    read = {rel: stored.get(rel, [False, []]) if files[rel] == snapshot.get(rel) else scan(os.path.join(root, rel))
            for rel in files}
    index = {}
    for rel in files:
        parts = os.path.splitext(rel)[0].split('/')
        parts = parts[:-1] if parts[-1] in ('__init__', 'index') else parts
        for i, _ in enumerate(parts):
            index.setdefault('/'.join(parts[i:]), []).append(rel)
    uses, users = {}, {}
    for rel, (_, names) in read.items():
        for name in names:
            for key in (name, os.path.splitext(name)[0], name.replace('.', '/')):
                for other in index.get(key, ()):
                    if other != rel:
                        uses.setdefault(rel, set()).add(other)
                        users.setdefault(other, set()).add(rel)
    shebang = {rel for rel, (flag, _) in read.items() if flag}
    return uses, users, shebang | set(uses) | set(users)


def sets(state, files):
    """(unchecked, entries, demanded, checked, uses, users); no line here tests the size of a set."""
    uses, users, nodes = lookup(state, files)
    changed = {rel for rel in files if files[rel] != state['snapshot'].get(rel)}
    demanded = close(changed, users) & nodes
    last = {rel: max(files[other][1] for other in close({rel}, uses) & changed) / 1e9 for rel in demanded}
    checked = {rel for rel in demanded
               if any(run['t'] > last[rel] and (run['all'] or rel in run['reach']) for run in state['runs'])}
    unchecked = demanded - checked
    entries = sorted(close(unchecked, users) - users.keys())
    return unchecked, entries, demanded, checked, uses, users


def message(unchecked, entries):
    return MESSAGE % (', '.join(sorted(unchecked)), ', '.join(entries) or 'the program or tests that use them')


# ---------------------------------------------------------------- rule

def failed(event):
    """A tool call that failed, or whose stdout or stderr holds an error marker."""
    out = event.get('tool_response')
    out = '\n'.join(str(out.get(k) or '') for k in ('stdout', 'stderr')) if isinstance(out, dict) else str(out or '')
    return event.get('hook_event_name') == 'PostToolUseFailure' or bool(ERROR.search(out))


def named(argv, cwd, root, files):
    """The files a run names: a file, a module, or every file under a directory."""
    found = set()
    for word in argv:
        for candidate in (word, word.replace('.', '/') + '.py' if re.fullmatch(r'[\w.]+', word) else word):
            path = absolute(candidate, cwd)
            rel = os.path.relpath(path, root).replace(os.sep, '/')
            found.update(f for f in files if f == rel or f.startswith(rel.rstrip('/') + '/') or rel == '.')
    return found


def record(state, event):
    """Note completed runs; return the message for a note, or ''."""
    root, tool, given = state['root'], event.get('tool_name'), event.get('tool_input') or {}
    cwd, now = event.get('cwd') or root, time.time()
    if event.get('hook_event_name') == 'PostToolUseFailure' and tool != 'Bash':
        return ''
    began, state['last'] = state.get('last', now), now  # a run began after the previous hook event, so a change it made is newer
    files = listing(root)
    if tool == 'Bash' and isinstance(given.get('command'), str) and not failed(event):
        uses = lookup(state, files)[0]
        for argv, _ in segments(given['command']):
            argv = strip_wrappers(argv)
            if argv and argv[0] == 'cd':
                cwd = absolute(argv[1], cwd) if len(argv) > 1 else os.path.expanduser('~')
            elif is_run(argv):
                program = named(argv, cwd, root, files)
                state['runs'] = (state['runs'] + [{'t': began, 'all': is_tester(argv) and not program,
                                                   'reach': sorted(close(program, uses))}])[-300:]
    unchecked, entries = sets(state, files)[:2]
    state['noted'] = [rel for rel in state['noted'] if rel in unchecked]
    target = given.get('file_path') or given.get('notebook_path')
    if tool in EDITORS and isinstance(target, str) and target:
        rel = os.path.relpath(absolute(target, cwd), root).replace(os.sep, '/')
        if rel in unchecked and rel not in state['noted']:
            state['noted'].append(rel)
            return message(unchecked, entries)
    return ''


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
                files = listing(root)
                scans = {rel: scan(os.path.join(root, rel)) for rel in files}
                state = {'root': root, 'snapshot': files, 'runs': [], 'noted': [],
                         'scan': {rel: s for rel, s in scans.items() if s[0] or s[1]}}
            state['last'] = time.time()
            save(path, state)
            return {}
        if 'snapshot' not in state:
            return {}
        if name in FINAL:
            if event.get('stop_hook_active'):
                return {}
            unchecked, entries = sets(state, listing(state['root']))[:2]
            return {'decision': 'block', 'reason': message(unchecked, entries)} if unchecked else {}
        text = record(state, event)
        save(path, state)
    if text:
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
