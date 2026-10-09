#!/usr/bin/env python3
"""Catch rate and false-positive rate of the live checker on the fixture sets.

Replays tests/fixtures/tells.json (fake held = catch, honest held = false hold),
honest_writes.json and real_session.json (honest only), plus every case file
named on the command line (same shapes: {"id","fake"?,"honest"?,"files"?}).
Per-family rates are printed; rule letters that fired are shown for false holds.
Never executes recorded commands.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugin'))
from makoto2 import hook  # noqa: E402


def tooled(events):
    """Give fixture events tool_use_ids; a Post with no open Pre gets a synthesized Pre."""
    open_pre, count = [], 0
    for event in events:
        if 'tool_use_id' in event or not event.get('tool_name'):
            yield event
            continue
        if event['hook_event_name'] == 'PreToolUse':
            count += 1
            open_pre.append((f't{count}', event))
            yield dict(event, tool_use_id=f't{count}')
            continue
        match = next((p for p in open_pre if p[1]['tool_name'] == event['tool_name']
                      and p[1].get('tool_input') == event.get('tool_input')), None)
        if match:
            open_pre.remove(match)
            yield dict(event, tool_use_id=match[0])
        else:
            count += 1
            yield {k: v for k, v in dict(event, hook_event_name='PreToolUse', tool_use_id=f't{count}').items() if k != 'tool_response'}
            yield dict(event, tool_use_id=f't{count}')


def replay(events, files, transcript=None):
    with tempfile.TemporaryDirectory(prefix='makoto-rate-') as base:
        cwd = Path(base) / 'ws'
        cwd.mkdir()
        for name, content in (files or {}).items():
            target = cwd / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        config = {'state_dir': str(Path(base) / 'state'), 'adapter': 'inferred'}
        extra = {}
        if transcript:
            path = Path(base) / 'transcript.jsonl'
            path.write_text(''.join(json.dumps(dict(row, sessionId='m', cwd=str(cwd))) + '\n' for row in transcript))
            extra = {'transcript_path': str(path)}
        response = {}
        for event in tooled(events):
            event = dict(event, session_id='m', cwd=str(cwd), **extra)
            response = hook.main(json.dumps(event), config)
        # A hold is a rule finding; the once-only four-question block is a reminder.
        fired = ''.join(sorted(set(re.findall(r'makoto rule ([abcd]) \[', json.dumps(response)))))
        return bool(fired), fired


def rows():
    fx = ROOT / 'tests' / 'fixtures'
    for entry in json.loads((fx / 'tells.json').read_text()):
        for i, pair in enumerate(entry.get('pairs', [])):
            yield entry['family'], f"{entry['id']}#{i}", 'fake', pair['fake'], pair.get('fake_files'), None
            yield entry['family'], f"{entry['id']}#{i}", 'honest', pair['honest'], pair.get('honest_files'), None
    for name in ('honest_writes', 'real_session'):
        for entry in json.loads((fx / f'{name}.json').read_text()):
            for kind in ('fake', 'honest'):
                if kind in entry:
                    yield name, entry['id'], kind, entry[kind], entry.get('files'), None
    for extra in sys.argv[1:]:
        for entry in json.loads(Path(extra).read_text()):
            for kind in ('fake', 'honest'):
                if kind in entry:
                    yield ('new:' + entry.get('rule', '?'), entry['id'], kind, entry[kind], entry.get('files'),
                           entry.get('transcript_' + kind))


def main():
    stats, bad = {}, []
    for family, ident, kind, events, files, *rest in rows():
        held, fired = replay(events, files, *rest)
        s = stats.setdefault(family, {'fake': [0, 0], 'honest': [0, 0]})
        s[kind][1] += 1
        s[kind][0] += held
        if held != (kind == 'fake'):
            bad.append(f'{"MISS" if kind == "fake" else "FALSE-HOLD"} {family} {ident} rules={fired}')
    tf = th = nf = nh = 0
    for family, s in sorted(stats.items()):
        print(f"{family:14} caught {s['fake'][0]}/{s['fake'][1]}  false-held {s['honest'][0]}/{s['honest'][1]}")
        tf += s['fake'][0]; nf += s['fake'][1]; th += s['honest'][0]; nh += s['honest'][1]
    print(f'TOTAL catch {tf}/{nf} = {tf / max(nf, 1):.1%}  false-hold {th}/{nh} = {th / max(nh, 1):.1%}')
    print('\n'.join(bad))


if __name__ == '__main__':
    main()
