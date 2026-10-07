"""Replay built sessions through the installed hooks; keep all state in tmp."""
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'plugin')]


def install(destination):
    return Path(shutil.copytree(ROOT / 'plugin', destination,
                               ignore=shutil.ignore_patterns('__pycache__')))


def routes(plugin):
    hooks = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks']
    return {name: [hook['command'] for group in groups for hook in group['hooks']
                   if hook['type'] == 'command'] for name, groups in hooks.items()}


def invoke(command, raw, plugin, state):
    env = dict(os.environ, MAKOTO_STATE_DIR=str(state), MAKOTO_ADAPTER='inferred',
               PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONPATH', None)
    if plugin is None:
        env.pop('CLAUDE_PLUGIN_ROOT', None)
    else:
        env['CLAUDE_PLUGIN_ROOT'] = str(plugin)
    start = time.perf_counter()
    result = subprocess.run(['sh', '-c', command], input=raw, capture_output=True,
                            env=env, cwd=state.parent)
    return result, (time.perf_counter() - start) * 1000


def replay_installed(plugin, state, events):
    commands = routes(plugin)
    for event in events:
        name = event['hook_event_name']
        assert commands.get(name), f'No installed route for {name}'
        raw = json.dumps(event).encode()
        for command in commands[name]:
            result, elapsed = invoke(command, raw, plugin, state)
            assert result.returncode == 0, result.stderr
            yield event, result.stdout, elapsed


def main():
    from test_built_pairs import CASES, build
    timings = []
    with tempfile.TemporaryDirectory(prefix='makoto-timings-') as tmp:
        root = Path(tmp)
        plugin = install(root / 'plugin')
        for index, (rule, kind, variant) in enumerate(CASES):
            for clean in (False, True):
                events, proposed = build(rule, kind, variant, clean)
                timings.extend(ms for _, _, ms in replay_installed(
                    plugin, root / f'state-{index}-{clean}', events + [proposed]))
    ordered = sorted(timings)
    print(f'calls={len(timings)} p50={statistics.median(timings):.3f} ms '
          f'p95={ordered[math.ceil(len(ordered) * .95) - 1]:.3f} ms '
          f'max={max(timings):.3f} ms')


if __name__ == '__main__':
    main()
