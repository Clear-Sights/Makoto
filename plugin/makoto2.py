"""Makoto: holds a final answer while a file changed this session, or a file that depends on it, has not been run since.

Live entry: cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m makoto2 (hooks/hooks.json): one native Claude Code hook event
on stdin, one JSON response on stdout. Hooks: SessionStart, UserPromptSubmit, PostToolUse, PostToolUseFailure, Stop,
SubagentStop.

State per session (one JSON file under a lock in MAKOTO_STATE_DIR): the map, and nothing else. One node per file under
the cwd: its size and mtime at session start, the start time of the last successful run that reached it, a failed flag,
a noted flag (an entry program an earlier note named), and the names its text gives for links. Links, from a file to a file it depends on: uses (import-style
lines: import, from, require, include, use, source, load), reads (a quoted string naming a project file by relative
path or base name with extension) and produced by (the same on a line with a write marker; from the data file to the
file that writes it). Links are read again for files that change. A run stamps its start time on every node it reaches
(a failed run sets the failed flag) and is forgotten, so the state is bounded by the tree.
Sets, computed without a test of their size (see sets):
  changed   = nodes that differ from their session-start size or time, and new files;
  demanded  = changed nodes that are runnable (interpreter extension or shebang) or linked by uses or reads, plus every
              node that reaches one through links;
  checked   = demanded nodes stamped after the latest change among the changed nodes they reach.
A run reaches the program it names plus what that depends on; a test runner with no program argument reaches the test
files (name holds test or spec, or under a folder test, tests, spec, __tests__) and what they depend on. One message
names demanded minus checked and the entry programs (used by no file) that reach it: a note after any tool call, only when
an entry program it names was named by no earlier note (the noted flag, on the entry program's node); a hold at Stop or SubagentStop, once (stop_hook_active admits). An error in
Makoto blocks a final answer or tool step, names the error and the one way to disable Makoto.
Probe (collect): after a completed tool call that leaves unchecked nodes, and at the final answer if any remain, Makoto
runs the entry programs itself: one srt call (MAKOTO_SRT, else srt on PATH; none found or any error: no probe) running,
in a temporary copy of the tree with no network and writes only in the copy, each entry program that a known
interpreter runs with no argument, whatever it imports (the sandbox is the gate). A pass (exit 0, no error
marker) stamps the nodes it reaches, silently. A fail adds the last 15 lines of its output to the message: in a note
once per distinct output (the hash on the entry program's node), always in the hold. A timeout, or a program not probed,
leaves the note and hold as above. A result counts only if the tree is unchanged since the copy.
"""
import contextlib
import hashlib
import json
import os
import re
import shlex
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

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
PROBE_SECONDS = 8
TAIL = 15
DISABLE = 'claude plugin disable makoto'
MESSAGE = 'Not run since a change: %s. Run %s and read the output.'
DOWNSTREAM = 'Not changed, but uses a changed file: %s. Check each against the change.'
FINAL = ('Stop', 'SubagentStop')
HANDLED = FINAL + ('PostToolUse', 'PostToolUseFailure', 'SessionStart', 'UserPromptSubmit')
INTERPRETERS = {'.py': 'python3', '.js': 'node', '.mjs': 'node', '.cjs': 'node', '.rb': 'ruby', '.pl': 'perl',
                '.php': 'php', '.sh': 'sh', '.bash': 'bash'}
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
QUOTED = re.compile(r'[\'"]([^\'"\s]+\.\w+)[\'"]')
WRITES = re.compile(r'>|[\'"][wa][bt+]*[\'"]|\b(?:write\w*|dump\w*|save\w*|to_csv|to_json)\b')
SCRIPTS = ('.py', '.js', '.mjs', '.cjs', '.ts', '.sh', '.bash', '.zsh', '.rb', '.pl', '.php', '.lua', '.r', '.ps1',
           '.jl', '.tcl', '.awk')
TOKEN = re.compile(r'[\w@\-]+(?:[./][\w\-]+)*')
TESTS = re.compile(r'(?:^|/)(?:tests?|spec|__tests__)/|(?:test|spec)[^/]*$')
SHELL = re.compile(r'#!.*\b(?:ba|z|da|k)?sh\b')
OPERAND = r'([^\s\'"<>|&;()$`]+)(?=[\s;|&)]|$)'  # an unquoted path
SHELL_WRITES = re.compile(r'(?:>>?[ \t]*|\btee\b(?:[ \t]+-\w+)*[ \t]+)' + OPERAND)
SHELL_READS = re.compile(r'(?<!<)<(?![<(])[ \t]*' + OPERAND)
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
    # A folder that holds CACHEDIR.TAG is a tool's cache (the Cache Directory Tagging Specification): not the user's files.
    caches = tuple(n[:-len('CACHEDIR.TAG')] for n in names if n.endswith('/CACHEDIR.TAG'))
    names = [n for n in names if not n.startswith(caches)] if caches else names
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


# ---------------------------------------------------------------- map and sets

def scan(path):
    """The link-bearing parts of one file's text: a shebang flag and the names its lines give."""
    result = {'shebang': False, 'uses': [], 'quotes': [], 'writes': []}
    try:
        with open(path, 'rb') as stream:
            data = stream.read(MAX_READ)
    except OSError:
        return result
    if b'\0' in data[:1024]:
        return result
    text = data.decode('utf-8', 'replace')
    result['shebang'] = text.startswith('#!')
    names = [t for m in IMPORT.finditer(text) for t in TOKEN.findall(m.group(1) or m.group(2)) if t not in NOISE]
    result['uses'] = list(dict.fromkeys(names))[:200]
    shell = path.endswith(('.sh', '.bash', '.zsh')) or bool(SHELL.match(text))
    for line in text.splitlines():
        if shell and not line.lstrip().startswith('#'):
            result['writes'].extend(SHELL_WRITES.findall(line))
            result['quotes'].extend(SHELL_READS.findall(line))
        result['writes' if WRITES.search(line) else 'quotes'].extend(q[2:] if q.startswith('./') else q
                                                                      for q in QUOTED.findall(line))
    result['quotes'], result['writes'] = (list(dict.fromkeys(result[k]))[:200] for k in ('quotes', 'writes'))
    return result


def refresh(state, files, begin=False):
    """The map for the files now: nodes kept, new files added (changed from the start), links read again for changed files."""
    old, state['nodes'] = state['nodes'], {}
    for rel, stat in files.items():
        node = old.get(rel) or {'start': stat if begin else None, 'ran': 0, 'failed': False, 'noted': False, 'named': False, 'hash': ''}
        state['nodes'][rel] = node
        if begin or stat != node['start']:
            node.update(scan(os.path.join(state['root'], rel)))


def close(seeds, edges):
    """The seeds and everything reached from them along edges."""
    order, seen = list(seeds), set(seeds)
    for item in order:
        for other in edges.get(item, ()):
            if other not in seen:
                seen.add(other)
                order.append(other)
    return seen


def lookup(nodes):
    """(links, users, linked): from each file the files it depends on, the reverse, and the files tied by uses or reads."""
    index, named = {}, {}
    for rel in nodes:
        parts = os.path.splitext(rel)[0].split('/')
        parts = parts[:-1] if parts[-1] in ('__init__', 'index') else parts
        for i, _ in enumerate(parts):
            index.setdefault('/'.join(parts[i:]), []).append(rel)
        for i, _ in enumerate(rel.split('/')):
            named.setdefault('/'.join(rel.split('/')[i:]), []).append(rel)
    links, tied = {}, set()
    for rel, node in nodes.items():
        for name in node['uses']:
            for key in (name, os.path.splitext(name)[0], name.replace('.', '/')):
                tied.update((rel, other) for other in index.get(key, ()) if other != rel)
        tied.update((rel, other) for name in node['quotes'] for other in named.get(name, ()) if other != rel)
    produced = {(other, rel) for rel, node in nodes.items() for name in node['writes'] for other in named.get(name, ())
                if other != rel}
    for a, b in tied | produced:
        links.setdefault(a, set()).add(b)
    users = {}
    for a, b in tied | produced:
        users.setdefault(b, set()).add(a)
    return links, users, {x for pair in tied for x in pair}


def sets(state, files):
    """(unchecked, entries); no line here tests the size of a set."""
    nodes = state['nodes']
    links, users, linked = lookup(nodes)
    changed = {rel for rel in files if files[rel] != nodes[rel]['start']}
    runnable = {rel for rel, node in nodes.items() if node['shebang'] or rel.lower().endswith(SCRIPTS)}
    demanded = close(changed, users) & (linked | runnable)
    last = {rel: max(files[other][1] for other in close({rel}, links) & changed) for rel in demanded}
    unchecked = demanded - {rel for rel in demanded if nodes[rel]['ran'] > last[rel]}
    return unchecked, sorted(close(unchecked, users) - users.keys())


def message(unchecked, entries, nodes):
    text = MESSAGE % (', '.join(sorted(unchecked)), ', '.join(entries) or 'the program or tests that use them')
    return text + ''.join(' A run of %s failed; it needs a run that succeeds.' % rel for rel in sorted(unchecked)
                          if nodes[rel]['failed'])


# ---------------------------------------------------------------- probe

def interpreter(root, rel, node):
    """The known interpreter that runs the file with no argument, or None."""
    name = INTERPRETERS.get(os.path.splitext(rel)[1].lower())
    if name is None and node['shebang']:
        try:
            with open(os.path.join(root, rel), 'rb') as stream:
                words = stream.readline(200).decode('utf-8', 'replace')[2:].split()
        except OSError:
            words = []
        words = words[1:] if words[:1] and os.path.basename(words[0]) == 'env' else words
        name = os.path.basename(words[0]) if words else ''
        name = 'python3' if name.startswith('python') else name if name in INTERPRETERS.values() else None
    return name if name and shutil.which(name) else None


def command(name, copy, rel):
    """The shell command that runs one entry program as its project would: a Python file sees every folder above it, so a
    module of a package resolves its own imports, and a Python test file runs under pytest when pytest is installed."""
    path = shlex.quote(os.path.join(copy, rel))
    if name != 'python3':
        return '%s %s' % (name, path)
    above = [os.path.join(copy, *rel.split('/')[:k]) for k in range(rel.count('/'), -1, -1)]
    runner = 'python3 -m pytest -q -p no:cacheprovider' if TESTS.search(rel.lower()) and shutil.which('pytest') else 'python3'
    return 'PYTHONPATH=%s %s %s' % (shlex.quote(os.pathsep.join(above)), runner, path)


def probe(state, files, cwd, entries, quiet):
    """Run the entry programs that can be probed in one srt call, in a temporary copy of the tree. A pass stamps the nodes
    it reached, and the nodes of a pass that printed nothing are added to quiet: their run showed nothing of the change; returns {entry program: last lines of its output} for the failures. A timeout, an error, a program that
    cannot be probed, or a tree that changed meanwhile gives no result for it."""
    root, nodes, srt = state['root'], state['nodes'], shutil.which(os.environ.get('MAKOTO_SRT') or 'srt')
    links = lookup(nodes)[0]
    reach = {e: close({e}, links) for e in entries}
    programs = {e: interpreter(root, e, nodes[e]) for e in entries}
    programs = {e: name for e, name in programs.items() if name}
    if not (srt and programs and len(files) < MAX_FILES and sum(info[0] for info in files.values()) <= MAX_BYTES):
        return {}
    start, token, here = time.time_ns(), uuid.uuid4().hex, os.path.relpath(cwd, root)
    here = '.' if here.startswith('..') else here
    copy, settings = tempfile.mkdtemp(prefix='makoto-copy-'), tempfile.mkstemp(prefix='makoto-srt-', suffix='.json')
    order, results = list(programs), {}
    try:
        for rel in files:
            os.makedirs(os.path.dirname(os.path.join(copy, rel)), exist_ok=True)
            shutil.copy2(os.path.join(root, rel), os.path.join(copy, rel))
        os.makedirs(os.path.join(copy, here), exist_ok=True)
        with os.fdopen(settings[0], 'w') as stream:
            json.dump({'network': {'allowedDomains': [], 'deniedDomains': []},
                       'filesystem': {'denyRead': [], 'allowWrite': [copy], 'denyWrite': []}}, stream)
        script = 'cd %s || exit 1; ' % shlex.quote(os.path.join(copy, here)) + ''.join(
            "%s </dev/null 2>&1; printf '\\n%s %d %%s\\n' $?; " % (command(programs[e], copy, e), token, i)
            for i, e in enumerate(order))
        child = subprocess.Popen([srt, '--settings', settings[1], '-c', script], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
                                 env={'PATH': os.environ.get('PATH', os.defpath), 'HOME': copy,
                                      'LANG': os.environ.get('LANG', 'C.UTF-8')})
        try:
            out = child.communicate(timeout=PROBE_SECONDS)[0]
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            out = child.communicate()[0]
        text = out.decode('utf-8', 'replace').replace(copy, root)  # the output names the real tree, so a repeat is a repeat
        parts = re.split('\\nPREFIX (\\d+) (\\d+)\\n'.replace('PREFIX', token), text)
        for k in range(0, len(parts) - 2, 3):
            results[order[int(parts[k + 1])]] = (int(parts[k + 2]), parts[k].strip('\n'))
        same = listing(root) == files
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return {}
    finally:
        shutil.rmtree(copy, ignore_errors=True)
        with contextlib.suppress(OSError):
            os.unlink(settings[1])
    if not same:
        return {}
    for e, (code, text) in results.items():
        if code == 0 and not ERROR.search(text):
            for rel in reach[e]:
                nodes[rel].update(ran=start, failed=False)
            if not text.strip():  # Makoto does not ask the model for a run it has seen show nothing: downstream() names the files
                quiet.update(reach[e])
    return {e: '\n'.join(text.splitlines()[-TAIL:]) for e, (code, text) in results.items() if code or ERROR.search(text)}


def downstream(state, files, quiet):
    """The note naming the files that use a changed file, were not changed, and are unchecked or only quietly run, once
    each; '' when it would name no new file."""
    nodes = state['nodes']
    links, users, _ = lookup(nodes)
    changed = {rel for rel in files if files[rel] != nodes[rel]['start']}
    kept = sorted((close(changed, users) - changed) & (sets(state, files)[0] | quiet))
    if all(nodes[rel].get('named') for rel in kept):
        return ''
    for rel in kept:
        nodes[rel]['named'] = True
    return DOWNSTREAM % '; '.join('%s (%s)' % (rel, ', '.join(sorted(close({rel}, links) & changed))) for rel in kept)


def failures(bad, entries):
    return ''.join('\nA run of %s in a sandboxed copy failed; the last %d lines of its output:\n%s' % (e, TAIL, bad[e])
                   for e in entries if e in bad) + ('\n(run in a sandbox with no network)' if bad else '')


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


EDIT_TOOLS = ('Write', 'Edit', 'MultiEdit', 'NotebookEdit')


def record(state, event):
    """Stamp the nodes completed runs reached; return the message for a note, or ''."""
    root, tool, given = state['root'], event.get('tool_name'), event.get('tool_input') or {}
    cwd, now = event.get('cwd') or root, time.time_ns()
    if event.get('hook_event_name') == 'PostToolUseFailure' and tool != 'Bash':
        return ''
    began, state['last'] = state['last'], now  # a run began after the previous hook event, so a change it made is newer
    files = listing(root)
    refresh(state, files)
    nodes = state['nodes']
    if tool == 'Bash' and isinstance(given.get('command'), str):
        bad, links = failed(event), lookup(nodes)[0]
        for argv, _ in segments(given['command']):
            argv = strip_wrappers(argv)
            if argv and argv[0] == 'cd':
                cwd = absolute(argv[1], cwd) if len(argv) > 1 else os.path.expanduser('~')
            elif is_run(argv):
                program = named(argv, cwd, root, files)
                if is_tester(argv):
                    program = program or {f for f in files if TESTS.search(f.lower())}
                for rel in close(program, links):
                    nodes[rel]['failed'] = bad
                    if not bad:
                        nodes[rel]['ran'] = began
    unchecked, entries = sets(state, files)
    quiet = set()
    bad = probe(state, files, cwd, entries, quiet) if unchecked and event.get('hook_event_name') == 'PostToolUse' else {}
    unchecked, entries = sets(state, files)
    # A failing test waits for the final answer: mid-change it states what the code did before the change (measured,
    # research/quiet on the research branch).
    new = [e for e in entries if e in bad and not TESTS.search(e.lower())
           and nodes[e]['hash'] != hashlib.sha256(bad[e].encode()).hexdigest()]
    # The plain note follows only the edit tools: measured, a note after a shell-made change costs more and gains
    # nothing (research/v622, research/observed on the research branch). A probe's failure is noted after any tool.
    fresh = [e for e in entries if tool in EDIT_TOOLS and e not in bad and not nodes[e]['noted']]
    for e in fresh:
        nodes[e]['noted'] = True
    for e in new:
        nodes[e]['hash'] = hashlib.sha256(bad[e].encode()).hexdigest()
    text = message(unchecked, entries, nodes) + failures({e: bad[e] for e in new}, entries) if fresh or new else ''
    for rel in unchecked if text else ():  # the message names them already: each fact is said once
        nodes[rel]['named'] = True
    # Without the sandbox the hold stays and names the same files; there the note only adds cost (measured,
    # research/downstream on the research branch).
    users = downstream(state, files, quiet) if shutil.which(os.environ.get('MAKOTO_SRT') or 'srt') else ''
    return '\n'.join(part for part in (text, users) if part)


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
            if 'nodes' not in state:
                root = event.get('cwd') or os.getcwd()
                state = {'root': root, 'nodes': {}}
                refresh(state, listing(root), begin=True)
            state['last'] = time.time_ns()
            save(path, state)
            return {}
        if 'nodes' not in state:
            return {}
        if name in FINAL:
            if event.get('stop_hook_active'):
                return {}
            refresh(state, files := listing(state['root']))
            unchecked, entries = sets(state, files)
            bad = probe(state, files, event.get('cwd') or state['root'], entries, set()) if unchecked else {}
            unchecked, entries = sets(state, files)
            save(path, state)
            return ({'decision': 'block', 'reason': message(unchecked, entries, state['nodes']) + failures(bad, entries)}
                    if unchecked else {})
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
