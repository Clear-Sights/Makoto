"""Plant faults per eval/RULES.md: copy a session and remove a reading an admitted step needed.

    python3 eval/plant.py corpus.jsonl base_results.jsonl plants.jsonl

base_results.jsonl is a run of the baseline: a step is admitted when it has no hold row. Each output line is a
session copy {"id": "<id>#P1", "plant": "P1", "step": <index in the copy>, "events": [...]}.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from label import READING, WRITERS, dumps  # noqa: E402

TOKEN = re.compile(r'[A-Za-z_][\w./-]{5,}')
CODE = ('.py', '.js', '.ts', '.sh')


def dependent(event):
    if event['hook_event_name'] == 'Stop':
        return True
    if event['hook_event_name'] != 'PreToolUse':
        return False
    if event['tool_name'] in WRITERS:
        return True
    command = str(event.get('tool_input', {}).get('command', ''))
    return event['tool_name'] == 'Bash' and ('git commit' in command or 'git push' in command)


def drop(events, calls):
    return [e for e in events if e.get('tool_use_id') not in calls]


def p1(events, held):
    for i, event in enumerate(events):
        if not dependent(event) or i in held or event['hook_event_name'] != 'PreToolUse':
            continue
        before = events[:i]
        for token in dict.fromkeys(TOKEN.findall(dumps(event['tool_input']))):
            sources = [e for e in before if e['hook_event_name'] == 'PostToolUse' and token in dumps(e.get('tool_response'))]
            elsewhere = any(token in dumps(e.get('prompt', '')) + dumps(e.get('tool_input')) for e in before) \
                or any(token in dumps(e.get('tool_response')) for e in before if e['hook_event_name'] == 'PostToolUse' and e not in sources)
            if len(sources) == 1 and not elsewhere:
                new = drop(events, {sources[0]['tool_use_id']})
                return new, new.index(event)
    return None


def p2(events, held):
    for i, event in enumerate(events):
        if not dependent(event) or i in held:
            continue
        if event['hook_event_name'] == 'PreToolUse' and not (event['tool_name'] == 'Bash'):
            continue
        before = events[:i]
        for j, edit in enumerate(before):
            if edit['hook_event_name'] != 'PreToolUse' or edit['tool_name'] not in WRITERS:
                continue
            target = str(edit['tool_input'].get('file_path', ''))
            base = target.rsplit('/', 1)[-1]
            if not target.endswith(CODE):
                continue
            runs = {e['tool_use_id'] for e in before[j + 1:] if e['hook_event_name'] == 'PreToolUse'
                    and e['tool_name'] == 'Bash' and base in str(e['tool_input'].get('command', ''))}
            if runs:
                new = drop(events, runs)
                return new, new.index(event)
    return None


def p3(events, held):
    for i, event in enumerate(events):
        if dependent(event) and i not in held:
            readings = {e['tool_use_id'] for e in events[:i] if e['hook_event_name'] == 'PreToolUse' and e['tool_name'] in READING}
            if readings:
                new = drop(events, readings)
                return new, new.index(event)
    return None


def main():
    corpus, results, out = sys.argv[1:4]
    held = {}
    for line in open(results):
        r = json.loads(line)
        held[r['id']] = {row['i'] for row in r['rows'] if row['kind'] == 'hold'}
    counts = {'P1': 0, 'P2': 0, 'P3': 0}
    with open(out, 'w') as sink:
        for line in open(corpus):
            session = json.loads(line)
            for name, make in (('P1', p1), ('P2', p2), ('P3', p3)):
                made = make(session['events'], held[session['id']])
                if made:
                    events, step = made
                    counts[name] += 1
                    sink.write(json.dumps({'id': session['id'] + '#' + name, 'plant': name, 'step': step, 'events': events}) + '\n')
    print(json.dumps(counts))


if __name__ == '__main__':
    main()
