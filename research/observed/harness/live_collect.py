"""mini (RULES15.md, AMEND15_1.md): Haiku workers on the unrun family at level 3 (gen_unrun.py), three arms: plain, lean3, mini.
call_worker, parse_stream, usable, log_spend and total_spend are research/raw/makoto_rule_d2/harness/live_d2.py's, byte for byte.

    python3 -I live_m15.py gen  --seeds A-B --levels unrun=3
    python3 -I live_m15.py run  --seeds A-B --levels unrun=3 [--arms plain,lean3,mini] [--workers K] [--cap USD]

Environment: LIVE (scratch root), OUT (raw data dir), PLUGIN_LEAN3, PLUGIN_MINI (plugin dirs), GEN (dir with gen_unrun.py).
"""
import argparse
import fcntl
import glob
import gzip
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

LIVE, OUT, PLUGIN_V621, PLUGIN_COLLECT, GEN = (os.environ[k] for k in ('LIVE', 'OUT', 'PLUGIN_V621', 'PLUGIN_COLLECT', 'GEN'))
CLI = '2.1.323'
MODEL = os.environ.get('MODEL', 'claude-haiku-5-5')
CAPRUN = '0.80'
SPEND = os.path.join(OUT, 'SPEND_COLLECT.tsv')
ARMS = ('plain', 'v621', 'collect')
MECHS = tuple(os.environ['FAMILIES'].split(','))
sha = lambda b: hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()
HOLD_RULE = re.compile(r'makoto rule (\w) \[')


def log_spend(tag, usd):
    with open(SPEND, 'a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write('%s\t%s\t%.6f\n' % (time.strftime('%Y-%m-%dT%H:%M:%S'), tag, usd or 0))


def total_spend():
    return sum(float(l.split('\t')[2]) for l in open(SPEND)) if os.path.exists(SPEND) else 0.0


def parse_stream(text):
    events = [json.loads(l) for l in text.splitlines() if l.startswith('{')]
    holds = []
    for e in events:
        if e.get('type') == 'system' and e.get('subtype') == 'hook_response':
            try:
                out = json.loads(e.get('stdout') or '{}')
            except ValueError:
                out = {}
            reason = out.get('reason') or (out.get('hookSpecificOutput') or {}).get('permissionDecisionReason') or ''
            if out.get('decision') == 'block' or (out.get('hookSpecificOutput') or {}).get('permissionDecision') == 'deny':
                holds.append({'hook': e.get('hook_name'), 'rules': sorted(set(HOLD_RULE.findall(reason))), 'reason': reason})
    return events, holds


def call_worker(arm, prompt, sc, raw, name, td, tgt, plugin_dirs):
    cmd = ['claude', '-p', prompt, '--model', MODEL, '--output-format', 'stream-json', '--verbose', '--include-hook-events', '--permission-mode', 'acceptEdits',
           '--allowedTools', 'Bash,Read,Write,Edit,Glob,Grep', '--tools', 'Bash,Read,Write,Edit,Glob,Grep', '--setting-sources', '', '--max-budget-usd', CAPRUN]
    state = os.path.join(sc, '..', 'state_' + name)
    env = dict(os.environ, DISABLE_AUTOUPDATER='1')
    if arm != 'plain':
        cmd += ['--plugin-dir', plugin_dirs[arm]]
        shutil.rmtree(state, ignore_errors=True)
        os.makedirs(state)
        env['MAKOTO_STATE_DIR'] = os.path.abspath(state)
    t0 = time.time()
    try:
        txt = subprocess.run(cmd, cwd=sc, capture_output=True, text=True, timeout=1500, env=env).stdout
    except subprocess.TimeoutExpired as e:
        txt = (e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout) or ''
    secs = round(time.time() - t0, 1)
    sp = os.path.join(raw, 'streams', name + '.jsonl.gz')
    gzip.open(sp, 'wt').write(txt)
    ev, holds = parse_stream(txt)
    res = next((e for e in ev if e.get('type') == 'result'), {})
    g = subprocess.run([sys.executable, os.path.join(td, 'grade.py')], cwd=tgt, capture_output=True, text=True, timeout=300)
    init = next((e for e in ev if e.get('type') == 'system' and e.get('subtype') == 'init'), {})
    journal = glob.glob(os.path.join(state, '*.jsonl')) if arm != 'plain' else []
    return dict(passed=g.returncode == 0, grade_exit=g.returncode, grade_stdout=g.stdout, grade_stderr=g.stderr[-500:],
                cost_usd=res.get('total_cost_usd') or 0, status=res.get('subtype') or 'no_result', is_error=bool(res.get('is_error')),
                result_text_head=(res.get('result') or '')[:300], seconds=secs, num_turns=res.get('num_turns'),
                models=sorted({k for e in ev if e.get('type') == 'result' for k in (e.get('modelUsage') or {})}),
                init_tools=init.get('tools'), init_plugins=[p.get('name') for p in init.get('plugins', [])],
                hook_responses=sum(e.get('subtype') == 'hook_response' for e in ev if e.get('type') == 'system'),
                holds=[{k: h[k] for k in ('hook', 'rules')} for h in holds], hold_reasons=[h['reason'] for h in holds],
                journal_files=len(journal), stream_sha256=sha(open(sp, 'rb').read()), rate_limited=('usage limit' in txt.lower()),
                cli_version=init.get('claude_code_version'))


def usable(r):
    """A result event exists, only the worker model ran, no usage-limit message, and the call did not die on an API error."""
    return (r['status'] not in ('no_result', 'error_during_execution') and r['models'] == [MODEL] and not r['rate_limited']
            and r.get('cli_version') == CLI)


def task_dir(mech, seed):
    return os.path.join(LIVE, 'tasks', 'unrun-unrun-%d' % seed if mech == 'unrun' else '%s-%d' % (mech, seed))


GENS = {'unrun': ['gen_unrun.py', '--mech', 'unrun', '--level', '3'], 'sigchange': ['gen_sigchange.py', '--users', '12'],
        'unrun_js': ['gen_unrun_js.py'], 'datachain': ['gen_datachain.py']}


def gen(seeds, levels=None):
    """Every family in FAMILIES on the seeds given."""
    os.makedirs(os.path.join(LIVE, 'tasks'), exist_ok=True)
    for mech in MECHS:
        script, *flags = GENS[mech]
        subprocess.run([sys.executable, '-I', os.path.join(GEN, script), os.path.join(LIVE, 'tasks')] + [str(x) for x in seeds] + flags,
                       check=True, stdout=subprocess.DEVNULL)
    print(sum(os.path.isdir(task_dir(m, x)) for m in MECHS for x in seeds), 'tasks')


def one(arm, mech, seed, level, raw, cap, plugin_dirs):
    name = '%s_%s_%d' % (arm, mech, seed)
    rp = os.path.join(raw, 'results', name + '.json')
    if os.path.exists(rp):
        return
    td = task_dir(mech, seed)
    goal = ' '.join(open(os.path.join(td, 'GOAL.md')).read().split())
    for attempt in (1, 2):
        if total_spend() >= cap:
            print('STOP: spend cap reached, skip', name, flush=True)
            return
        sc = os.path.join(LIVE, 'scr', name)
        shutil.rmtree(sc, ignore_errors=True)
        os.makedirs(sc)
        tgt = os.path.join(sc, 'target')
        shutil.copytree(os.path.join(td, 'repo'), tgt)
        prompt = 'Goal and target: %s %s' % (goal, tgt)
        open(os.path.join(raw, 'requests', name + '.txt'), 'w').write(prompt)
        r = {'arm': arm, 'mech': mech, 'seed': seed, 'level': level, 'attempt': attempt, 'request_sha256': sha(prompt), 'prompt_chars': len(prompt)}
        r.update(call_worker(arm, prompt, sc, raw, name + ('' if attempt == 1 else '_retry'), td, tgt, plugin_dirs))
        log_spend('%s/%s' % (name, attempt), r['cost_usd'])
        r['usable'] = bool(usable(r))
        shutil.copytree(tgt, os.path.join(raw, 'targets', name + ('' if attempt == 1 else '_retry')), ignore=shutil.ignore_patterns('__pycache__'))
        shutil.rmtree(sc, ignore_errors=True)
        shutil.rmtree(os.path.join(sc, '..', 'state_' + name), ignore_errors=True)
        if r['usable'] or attempt == 2:
            json.dump(r, open(rp, 'w'), indent=1)
            print(name, r['passed'], r['status'], '%.4f' % r['cost_usd'], '%.0fs' % r['seconds'], 'holds', len(r['holds']), 'usable', r['usable'], flush=True)
            return


def run(a, seeds, levels):
    raw = os.path.join(OUT, 'live')
    for d in ('requests', 'streams', 'results', 'targets'):
        os.makedirs(os.path.join(raw, d), exist_ok=True)
    plugin_dirs = {'v621': PLUGIN_V621, 'collect': PLUGIN_COLLECT}
    arms = a.arms.split(',')
    rng = random.Random('collect-order')
    jobs = []
    for mech in MECHS:
        for s in seeds:
            order = list(ARMS)
            rng.shuffle(order)
            jobs += [(arm, mech, s) for arm in order if arm in arms]
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(lambda j: one(j[0], j[1], j[2], 0, raw, a.cap, plugin_dirs), jobs))
    print('spend_total', total_spend())


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('--seeds', required=True)
    ap.add_argument('--levels', default='unrun=3,sigchange=1')
    ap.add_argument('--arms', default=','.join(ARMS))
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--cap', type=float, default=25.0)
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.seeds.split('-'))
    levels = {k: int(v) for k, v in (p.split('=') for p in a.levels.split(','))}
    gen(range(lo, hi + 1), levels) if a.cmd == 'gen' else run(a, range(lo, hi + 1), levels)
