"""Cost of Makoto's hook on the events the tests already contain.

Two modes. `cold` runs as the tests do (PYTHONDONTWRITEBYTECODE=1, so every call compiles
plugin/makoto2.py). `warm` lets Python cache bytecode, as an installed plugin directory does.

Per hook call: wall time in ms (whole `bash -c` command from hooks.json, so it includes
interpreter start and import) and bytes added to the model's context (the UTF-8 length of
additionalContext + reason + systemMessage in the reply). Each scenario is replayed REPEAT
times in a fresh state directory; the reported ms is the median over those runs.

    MEASURE_REPEAT=5 python3 scripts/measure_cost.py [--json out.json]
"""
import json
import os
import subprocess
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_rules import CASES, HOOKS, PLUGIN, ev, read  # noqa: E402
from test_robust import WRITE_STEP  # noqa: E402

REPEAT = int(os.environ.get('MEASURE_REPEAT', '5'))


def send(tmp, event, warm=False):
    """One event through the command hooks.json registers for it (as tests/test_rules.send)."""
    command = HOOKS[event['hook_event_name']][0]['hooks'][0]['command']
    env = {k: v for k, v in os.environ.items() if not k.startswith('MAKOTO_') and k != 'PYTHONDONTWRITEBYTECODE'}
    env.update(CLAUDE_PLUGIN_ROOT=str(PLUGIN), MAKOTO_STATE_DIR=str(tmp / 'state'))
    if not warm:
        env['PYTHONDONTWRITEBYTECODE'] = '1'
    run = subprocess.run(['bash', '-c', command], input=json.dumps(event), env=env, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def scenarios():
    for rule, (plant, twin) in sorted(CASES.items()):
        yield f'rule-{rule}-plant', plant
        yield f'rule-{rule}-twin', twin
    yield 'admitted-write', read('source data') + [WRITE_STEP]


def context_bytes(reply):
    out = reply.get('hookSpecificOutput', {}).get('additionalContext', '') + reply.get('reason', '') + reply.get('systemMessage', '')
    return len(out.encode('utf-8'))


def measure(warm=False):
    rows = {}  # (scenario, index) -> {'hook', 'ms': [], 'bytes'}
    for name, events in scenarios():
        for _ in range(REPEAT):
            with tempfile.TemporaryDirectory() as tmp:
                for i, event in enumerate(events):
                    start = time.perf_counter()
                    reply = send(Path(tmp), event, warm)
                    ms = (time.perf_counter() - start) * 1000
                    row = rows.setdefault((name, i), {'hook': event['hook_event_name'], 'ms': [], 'bytes': context_bytes(reply)})
                    row['ms'].append(ms)
                    assert row['bytes'] == context_bytes(reply), 'context size must be deterministic'
    return rows


def report(rows):
    by_hook = {}
    for row in rows.values():
        h = by_hook.setdefault(row['hook'], {'n': 0, 'ms': [], 'bytes': 0})
        h['n'] += 1
        h['ms'].append(statistics.median(row['ms']))
        h['bytes'] += row['bytes']
    lines = ['hook                 n   median ms   mean bytes/call   total bytes']
    for hook, h in sorted(by_hook.items()):
        lines.append(f"{hook:<18} {h['n']:>3} {statistics.median(h['ms']):>11.1f} {h['bytes'] / h['n']:>17.1f} {h['bytes']:>13}")
    total_ms = sum(statistics.median(r['ms']) for r in rows.values())
    total_bytes = sum(r['bytes'] for r in rows.values())
    lines.append(f"suite: {len(rows)} calls, {total_ms:.0f} ms summed (median per call), {total_bytes} bytes added to context")
    return '\n'.join(lines), {'calls': len(rows), 'ms': total_ms, 'bytes': total_bytes,
                              'by_hook': {k: {'n': v['n'], 'median_ms': statistics.median(v['ms']), 'bytes': v['bytes']} for k, v in by_hook.items()}}


if __name__ == '__main__':
    out = {}
    for mode in ('cold', 'warm'):
        if mode == 'warm':  # one untimed pass fills the bytecode cache
            for _name, events in scenarios():
                with tempfile.TemporaryDirectory() as tmp:
                    for event in events:
                        send(Path(tmp), event, True)
        text, out[mode] = report(measure(mode == 'warm'))
        print(f'[{mode}]\n{text}')
    if '--json' in sys.argv:
        Path(sys.argv[sys.argv.index('--json') + 1]).write_text(json.dumps(out, indent=1))
