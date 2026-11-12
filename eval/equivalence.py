"""Differential equivalence of two Makoto builds: every hook response must be identical. No model is called.

    python3 eval/equivalence.py corpus --old DIR --new DIR --corpus corpus.jsonl [--log out.jsonl]
    python3 eval/equivalence.py tests  --old DIR --new DIR --tests DIR [--log out.jsonl] [-- pytest args]
    python3 eval/equivalence.py fuzz   --old DIR --new DIR [--sessions 500] [--seed 1] [--log out.jsonl]

DIR holds makoto2.py (a plugin directory). Exit status 1 when any response differs.

corpus: each session's events go, in order, through the main() of both builds, each with a fresh state
directory, and the two responses are compared as JSON.

fuzz: random sessions of edits, runs, reads, shell moves, commits and final answers over real files in a temporary
directory, answered by both builds in-process and compared as in corpus.

tests: runs the pytest files in TESTS twice, once with every hook command (`bash -c <hooks.json command>`)
redirected to the OLD build and once to the NEW build, in the same base directory, each build keeping its own
state. Every hook call is logged with its test, its place in the test, its stdin, stdout and exit code, and the
two logs are compared call by call. The tests may pass or fail: only the comparison counts, and a test that
makes a different number of hook calls in the two runs is a difference too.
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def load(directory, name):
    spec = importlib.util.spec_from_file_location(name, str(Path(directory) / 'makoto2.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(log, row):
    with open(log, 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + '\n')


# ----------------------------------------------------------------------
# pytest plugin: redirect the hook command to one build and log each call.

def pytest_configure(config):
    root, log = os.environ.get('EQUIV_ROOT'), os.environ.get('EQUIV_LOG')
    if not (root and log):
        return
    real = subprocess.run
    counts = {}

    def run(args, *a, **kw):
        command = args[2] if isinstance(args, (list, tuple)) and len(args) == 3 and args[:2] == ['bash', '-c'] else ''
        if 'makoto2' not in command:
            return real(args, *a, **kw)
        result = real(args, *a, **dict(kw, env=dict(kw.get('env') or os.environ, CLAUDE_PLUGIN_ROOT=root)))
        test = os.environ.get('PYTEST_CURRENT_TEST', '').rsplit(' ', 1)[0]
        counts[test] = counts.get(test, 0) + 1
        record(log, {'test': test, 'n': counts[test], 'input': kw.get('input'), 'stdout': result.stdout, 'code': result.returncode})
        return result

    subprocess.run = run


# ----------------------------------------------------------------------

def corpus(args):
    old, new = load(args.old, 'makoto2_old'), load(args.new, 'makoto2_new')
    total = differ = 0
    for line in open(args.corpus, encoding='utf-8'):
        session = json.loads(line)
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            cfg_old, cfg_new = dict(old.CONFIG, state_dir=a, checkpoint=True), dict(new.CONFIG, state_dir=b, checkpoint=True)
            for i, event in enumerate(session['events']):
                raw = json.dumps(event)
                x = json.dumps(old.main(raw, cfg_old), sort_keys=True)
                y = json.dumps(new.main(raw, cfg_new), sort_keys=True)
                total += 1
                if x != y:
                    differ += 1
                    if args.log:
                        record(args.log, {'session': session['id'], 'i': i, 'old': x, 'new': y})
    print('corpus: %d responses compared, %d differ' % (total, differ))
    return differ


FILES = ['a.py', 'b.py', 'pkg/__init__.py', 'pkg/m.py', 'c.json', 'd.sh', 'e.txt', 'run', 'f.js', 'g.go', 'h.toml']
CODE = {'a.py': 'import pkg.m\nprint(pkg.m.X)\n', 'b.py': 'import a\n', 'pkg/__init__.py': '', 'pkg/m.py': 'X = 1\n',
        'c.json': '{"k": 1}\n', 'd.sh': '#!/bin/sh\necho 1\n', 'e.txt': 'notes\n', 'run': '#!/bin/sh\necho 1\n', 'f.js': 'console.log(1)\n',
        'g.go': 'package main\n', 'h.toml': 'k = 1\n'}
COMMANDS = ['python3 {f}', 'python {f}', 'node {f}', 'sh {f}', './{f}', 'cat {f}', 'head -3 {f}', 'pytest {f}', 'python3 -m pkg.m', 'python3 -m a',
            'python3 -c "import pkg.m"', 'python3 -c "import json; print(json.load(open(\'{f}\')))"', 'go run {f}', 'git add {f}',
            'git add -A', 'git commit -m x', 'git commit -am x', 'git push origin main', 'git status --porcelain', 'rm {f}', 'rm -r pkg',
            'mv {f} {g}', 'cp {f} {g}', 'touch {f}', 'echo 1 > {f}', 'sed -i s/1/2/ {f}', 'python3 {f} && python3 {g}', 'python3 {f} || true',
            'cd pkg && python3 m.py', 'ls', 'false', 'python3 {f} 2>&1 | tail -1']


def fuzz(args):
    import random
    old, new = load(args.old, 'makoto2_old'), load(args.new, 'makoto2_new')
    rng = random.Random(args.seed)
    total = differ = 0
    for n in range(args.sessions):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b, tempfile.TemporaryDirectory() as cwd:
            cfg = [dict(m.CONFIG, state_dir=d, checkpoint=n % 2 == 0) for m, d in ((old, a), (new, b))]
            for name in FILES:
                (Path(cwd) / name).parent.mkdir(parents=True, exist_ok=True)
                (Path(cwd) / name).write_text(CODE[name])
            events = []
            for i in range(rng.randint(3, 25)):
                f, g = rng.choice(FILES), rng.choice(FILES)
                agent = {'agent_id': rng.choice(['w1', 'w2'])} if n % 3 == 0 else {}
                kind = rng.random()
                tid = 't%d' % i
                if kind < 0.3:
                    tool, ti = rng.choice([('Write', {'file_path': f, 'content': rng.choice([CODE[f], '#!/bin/sh\n', '{"a": 1}', 'x = 2\n'])}),
                                           ('Edit', {'file_path': f, 'old_string': 'x', 'new_string': 'y'}),
                                           ('NotebookEdit', {'notebook_path': 'n.ipynb', 'new_source': 'x = 1'})])
                elif kind < 0.45:
                    tool, ti = 'Read', rng.choice([{'file_path': f}, {'file_path': f, 'limit': 2}])
                else:
                    tool, ti = 'Bash', {'command': rng.choice(COMMANDS).format(f=f, g=g)}
                resp = rng.choice([{'stdout': '1\n', 'exitCode': 0}, {'stdout': '', 'stderr': 'boom', 'exitCode': 1}, {'content': 'ok'}, {'stdout': ''}])
                base = dict(session_id='s%d' % n, cwd=cwd, **agent)
                pre = dict(base, hook_event_name='PreToolUse', tool_name=tool, tool_use_id=tid, tool_input=ti)
                events.append(pre)
                if rng.random() < 0.9:
                    events.append(dict(pre, hook_event_name='PostToolUseFailure' if rng.random() < 0.1 else 'PostToolUse', tool_response=resp))
                if rng.random() < 0.25:
                    events.append(dict(base, hook_event_name=rng.choice(['Stop', 'SubagentStop', 'PreDelivery']), last_assistant_message='Done %s' % f,
                                       stop_hook_active=rng.random() < 0.5))
            events.append(dict(session_id='s%d' % n, cwd=cwd, hook_event_name='Stop', last_assistant_message='Done'))
            for event in events:
                raw = json.dumps(event)
                x = json.dumps(old.main(raw, cfg[0]), sort_keys=True)
                y = json.dumps(new.main(raw, cfg[1]), sort_keys=True)
                total += 1
                if x != y:
                    differ += 1
                    if args.log:
                        record(args.log, {'session': n, 'event': event, 'old': x, 'new': y})
    print('fuzz: %d sessions, %d responses compared, %d differ' % (args.sessions, total, differ))
    return differ


def tests(args, extra):
    log = Path(args.log) if args.log else Path(tempfile.mkdtemp()) / 'log.jsonl'
    base = Path(tempfile.gettempdir()) / 'equivalence_base'
    rows, tails = {}, {}
    for role, root in (('old', args.old), ('new', args.new)):
        path = log.with_name(log.stem + '.' + role + '.jsonl')
        path.unlink(missing_ok=True)
        shutil.rmtree(base, ignore_errors=True)
        env = dict(os.environ, EQUIV_ROOT=str(Path(root).resolve()), EQUIV_LOG=str(path.resolve()),
                   PYTHONPATH=str(Path(__file__).resolve().parent) + os.pathsep + os.environ.get('PYTHONPATH', ''),
                   PYTHONDONTWRITEBYTECODE='1')
        run = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'equivalence', '-p', 'no:cacheprovider',
                              '--basetemp=' + str(base), str(args.tests), *extra], env=env, capture_output=True, text=True)
        tails[role] = (run.stdout.strip().splitlines() or [''])[-1]
        rows[role] = {}
        if path.exists():
            for line in open(path, encoding='utf-8'):
                row = json.loads(line)
                rows[role][(row['test'], row['n'])] = row
    differ = [k for k in sorted(set(rows['old']) | set(rows['new']))
              if k not in rows['old'] or k not in rows['new']
              or any(rows['old'][k][f] != rows['new'][k][f] for f in ('input', 'stdout', 'code'))]
    print('tests %s: %d hook calls compared, %d differ; pytest old: %s; new: %s'
          % (args.tests, len(rows['old']), len(differ), tails['old'], tails['new']))
    for k in differ[:20]:
        print('  DIFF', k, '\n    old:', str(rows['old'].get(k, {}).get('stdout'))[:300], '\n    new:', str(rows['new'].get(k, {}).get('stdout'))[:300])
    return len(differ)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=('corpus', 'tests', 'fuzz'))
    ap.add_argument('--old', required=True)
    ap.add_argument('--new', required=True)
    ap.add_argument('--corpus')
    ap.add_argument('--tests')
    ap.add_argument('--log')
    ap.add_argument('--sessions', type=int, default=500)
    ap.add_argument('--seed', type=int, default=1)
    args, extra = ap.parse_known_args()
    differ = corpus(args) if args.mode == 'corpus' else fuzz(args) if args.mode == 'fuzz' else tests(args, [e for e in extra if e != '--'])
    sys.exit(1 if differ else 0)


if __name__ == '__main__':
    main()
