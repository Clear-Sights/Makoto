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
One message names demanded minus checked and the entry programs (used by no file) that reach it. There is no note.
At Stop or SubagentStop Makoto runs those entry programs itself (see probes): in a temporary copy of the tree, with a
scrubbed environment, closed input and no network, only programs a known interpreter runs with no argument, and never
one that reaches an outward file (a network or process library in the lookup). A pass checks the files it reaches and
admits silently. A failure holds with the message and the last lines of the output, at most 3 times per final answer.
What no probe checked is held once as the message (stop_hook_active admits); without network isolation there is no
probe. An error in Makoto blocks a final answer or tool step, names the error and the one way to disable Makoto.
"""
import contextlib
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
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
MAX_BYTES = 50 * 1024 * 1024
PROBE_SECONDS = 5
PROBE_BUDGET = 22
MAX_HOLDS = 3
TAIL = 15
DISABLE = 'claude plugin disable makoto'
MESSAGE = 'Not run since a change: %s. Run %s and read the output.'
FINAL = ('Stop', 'SubagentStop')
HANDLED = FINAL + ('PostToolUse', 'PostToolUseFailure', 'SessionStart', 'UserPromptSubmit')
OUTWARD = frozenset('socket ssl http urllib requests httpx aiohttp websockets ftplib smtplib paramiko boto3 grpc net/http '
                    'axios node-fetch fetch net dgram open-uri subprocess multiprocessing child_process os/exec pty'.split())
INTERPRETERS = {'py': 'python3', 'js': 'node', 'mjs': 'node', 'cjs': 'node', 'rb': 'ruby', 'pl': 'perl', 'php': 'php',
                'sh': 'sh', 'bash': 'bash'}
ISOLATIONS = (['unshare', '-rn'], ['sandbox-exec', '-n', 'no-network'])
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
    """(uses, users, nodes, outward): which file uses which, and the files in the lookup or with a shebang."""
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
    outward = {rel for rel, (_, names) in read.items() if any(n in OUTWARD or re.split('[./]', n)[0] in OUTWARD for n in names)}
    return uses, users, shebang | set(uses) | set(users), outward


def sets(state, files):
    """(unchecked, entries, uses, outward); no line here tests the size of a set."""
    uses, users, nodes, outward = lookup(state, files)
    changed = {rel for rel in files if files[rel] != state['snapshot'].get(rel)}
    demanded = close(changed, users) & nodes
    last = {rel: max(files[other][1] for other in close({rel}, uses) & changed) / 1e9 for rel in demanded}
    checked = {rel for rel in demanded
               if any(run['t'] > last[rel] and (run['all'] or rel in run['reach']) for run in state['runs'])}
    unchecked = demanded - checked
    entries = sorted(close(unchecked, users) - users.keys())
    return unchecked, entries, uses, outward


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
    """Note completed runs that succeeded."""
    root, tool, given = state['root'], event.get('tool_name'), event.get('tool_input') or {}
    cwd, now = event.get('cwd') or root, time.time()
    if event.get('hook_event_name') == 'PostToolUseFailure' and tool != 'Bash':
        return
    began, state['last'] = state.get('last', now), now  # a run began after the previous hook event, so a change it made is newer
    if tool == 'Bash' and isinstance(given.get('command'), str) and not failed(event):
        files = listing(root)
        uses = lookup(state, files)[0]
        for argv, _ in segments(given['command']):
            argv = strip_wrappers(argv)
            if argv and argv[0] == 'cd':
                cwd = absolute(argv[1], cwd) if len(argv) > 1 else os.path.expanduser('~')
            elif is_run(argv):
                program = named(argv, cwd, root, files)
                state['runs'] = (state['runs'] + [{'t': began, 'all': is_tester(argv) and not program,
                                                   'reach': sorted(close(program, uses))}])[-300:]


# ---------------------------------------------------------------- probes

def isolation():
    """The command prefix that cuts the network and works here, or None."""
    for prefix in ISOLATIONS:
        try:
            if shutil.which(prefix[0]) and subprocess.run(prefix + ['true'], capture_output=True, timeout=5).returncode == 0:
                return prefix
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def command(root, rel):
    """How a known interpreter runs the file with no argument, or None."""
    path = os.path.join(root, rel)
    name = INTERPRETERS.get(rel.rpartition('.')[2].lower()) if '.' in os.path.basename(rel) else None
    if name is None:
        words = scan_first_line(path).split()
        words = words[1:] if words[:1] and os.path.basename(words[0]) == 'env' else words
        name = os.path.basename(words[0]) if words else None
        name = name if name in INTERPRETERS.values() else None
    return [name, rel] if name and shutil.which(name) else None


def scan_first_line(path):
    try:
        with open(path, 'rb') as stream:
            line = stream.readline(200).decode('utf-8', 'replace')
    except OSError:
        return ''
    return line[2:].strip() if line.startswith('#!') else ''


def copy_tree(root, files, target):
    for rel in files:
        os.makedirs(os.path.dirname(os.path.join(target, rel)), exist_ok=True)
        shutil.copy2(os.path.join(root, rel), os.path.join(target, rel))


def probes(state, files, cwd, entries, uses, outward):
    """Run each entry program that may be probed, in a no-network copy of the tree: (reaches of those that passed,
    [(program, last output lines)] of those that failed). Programs that time out or cannot be probed are in neither."""
    root = state['root']
    prefix = isolation()
    programs = [e for e in entries if not close({e}, uses) & outward and command(root, e)]
    if not (prefix and programs and len(files) < MAX_FILES and sum(f[0] for f in files.values()) <= MAX_BYTES):
        return [], []
    passed, failed, deadline = [], [], time.monotonic() + PROBE_BUDGET
    temp = tempfile.mkdtemp(prefix='makoto-probe-')
    try:
        copy_tree(root, files, os.path.join(temp, 'tree'))
        here = os.path.join(temp, 'tree', os.path.relpath(cwd, root)) if cwd.startswith(root + os.sep) else os.path.join(temp, 'tree')
        os.makedirs(here, exist_ok=True)
        env = {'PATH': os.environ.get('PATH', os.defpath), 'HOME': temp, 'LANG': os.environ.get('LANG', 'C.UTF-8')}
        for program in programs:
            seconds = min(PROBE_SECONDS, deadline - time.monotonic())
            if seconds <= 0:
                break
            child = subprocess.Popen(prefix + [command(root, program)[0], os.path.join(temp, 'tree', program)],
                                     cwd=here, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            try:
                out = child.communicate(timeout=seconds)[0].decode('utf-8', 'replace')
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.communicate()
                continue
            if child.returncode or ERROR.search(out):
                failed.append((program, '\n'.join(out.splitlines()[-TAIL:])))
            else:
                passed.append(sorted(close({program}, uses)))
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    return passed, failed


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
                state = {'root': root, 'snapshot': files, 'runs': [],
                         'scan': {rel: s for rel, s in scans.items() if s[0] or s[1]}}
            state['last'] = time.time()
            save(path, state)
            return {}
        if 'snapshot' not in state:
            return {}
        if name in FINAL:
            root, active = state['root'], event.get('stop_hook_active')
            files = listing(root)
            unchecked, entries, uses, outward = sets(state, files)
            state['holds'] = state.get('holds', 0) if active else 0
            passed, failed = probes(state, files, event.get('cwd') or root, entries, uses, outward)
            if failed:
                state['holds'] += 1
                reply = {} if state['holds'] > MAX_HOLDS else {'decision': 'block', 'reason': message(unchecked, entries) + ''.join(
                    '\nProbe of %s failed; the last %d lines of its output:\n%s' % (p, TAIL, tail) for p, tail in failed)}
            else:
                state['runs'] += [{'t': time.time(), 'all': False, 'reach': reach} for reach in passed]
                unchecked, entries = sets(state, files)[:2]
                reply = {'decision': 'block', 'reason': message(unchecked, entries)} if unchecked and not active else {}
            save(path, state)
            return reply
        record(state, event)
        save(path, state)
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
