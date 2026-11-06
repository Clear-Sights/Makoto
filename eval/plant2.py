"""Plants for recall per eval/RULES2.md.

    python3 eval/plant2.py corpus.jsonl unplanted_results.jsonl plants2.jsonl
    python3 eval/plant2.py --count plants2.jsonl planted_results.jsonl
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stats import show  # noqa: E402

EDITS = ('Edit', 'MultiEdit')
WRITERS = ('Write', 'Edit', 'MultiEdit', 'NotebookEdit')
TOKEN = re.compile(r'[A-Za-z_][\w./-]{5,}')
CODE = ('.py', '.js', '.ts', '.sh')


def flat(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def target(event):
    return str(event.get('tool_input', {}).get('file_path', ''))


def needs_reading(events, i):
    """(F, read tool_use_ids) when events[i] is a qualifying Q1 step, else None."""
    event = events[i]
    if event['hook_event_name'] != 'PreToolUse' or event['tool_name'] not in EDITS + ('Write',):
        return None
    if event['tool_name'] == 'Write':
        post = next((e for e in events[i + 1:] if e.get('tool_use_id') == event['tool_use_id'] and e['hook_event_name'] == 'PostToolUse'), None)
        if not post or post.get('tool_response', {}).get('type') != 'update':
            return None
    path = target(event)
    before = events[:i]
    if any(e['hook_event_name'] == 'PreToolUse' and e['tool_name'] in WRITERS and target(e) == path for e in before):
        return None
    reads = {e['tool_use_id'] for e in before if e['hook_event_name'] == 'PreToolUse' and e['tool_name'] == 'Read' and target(e) == path}
    return (path, reads) if reads else None


def drop(events, calls):
    return [e for e in events if e.get('tool_use_id') not in calls]


def main():
    if sys.argv[1] == '--count':
        plants = {json.loads(l)['id']: json.loads(l) for l in open(sys.argv[2])}
        results = {json.loads(l)['id']: json.loads(l) for l in open(sys.argv[3])}
        n, caught = Counter(), Counter()
        for pid, plant in plants.items():
            n[plant['plant']] += 1
            n['all'] += 1
            if any(r['kind'] == 'hold' and r['i'] == plant['step'] for r in results[pid]['rows']):
                caught[plant['plant']] += 1
                caught['all'] += 1
        for key in sorted(n):
            print(key, show(caught[key], n[key]))
        return
    corpus, results, out = sys.argv[1:4]
    held = {}
    for line in open(results):
        r = json.loads(line)
        held[r['id']] = {row['i'] for row in r['rows'] if row['kind'] == 'hold'}
    counts = Counter()
    with open(out, 'w') as sink:
        for line in open(corpus):
            session = json.loads(line)
            events, admitted = session['events'], held[session['id']]

            def emit(kind, new, step):
                counts[kind] += 1
                sink.write(json.dumps({'id': session['id'] + '#' + kind, 'plant': kind, 'step': new.index(step), 'events': new}) + '\n')

            q1 = q3 = q2 = False
            for i, event in enumerate(events):
                if i in admitted:
                    continue
                found = needs_reading(events, i)
                if found and not q1:
                    q1 = True
                    emit('Q1', drop(events, found[1]), event)
                if found and not q3:
                    before = events[:i]
                    for token in dict.fromkeys(TOKEN.findall(flat(event['tool_input']))):
                        sources = [e for e in before if e['hook_event_name'] == 'PostToolUse' and token in flat(e.get('tool_response'))]
                        elsewhere = any(token in flat(e.get('prompt', '')) + flat(e.get('tool_input')) for e in before) or any(
                            token in flat(e.get('tool_response')) for e in before if e['hook_event_name'] == 'PostToolUse' and e not in sources)
                        if len(sources) == 1 and not elsewhere:
                            q3 = True
                            emit('Q3', drop(events, {sources[0]['tool_use_id']}), event)
                            break
                if event['hook_event_name'] == 'Stop' and not q2:
                    for j, edit in enumerate(events[:i]):
                        if edit['hook_event_name'] != 'PreToolUse' or edit['tool_name'] not in WRITERS or not target(edit).endswith(CODE):
                            continue
                        base = target(edit).rsplit('/', 1)[-1]
                        runs = {e['tool_use_id'] for e in events[j + 1:i] if e['hook_event_name'] == 'PreToolUse'
                                and e['tool_name'] == 'Bash' and base in str(e['tool_input'].get('command', ''))}
                        if runs:
                            q2 = True
                            emit('Q2', drop(events, runs), event)
                            break
    print(json.dumps(counts))


if __name__ == '__main__':
    main()
