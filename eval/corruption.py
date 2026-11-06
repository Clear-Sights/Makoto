"""Compare a run with the journal corrupted mid-session against the same plugin's uncorrupted run.

    python3 eval/corruption.py corpus.jsonl uncorrupted.jsonl corrupted.jsonl

Counts, over the events after the corruption point: error blocks (every one is a false positive, since no rule
found anything), rule holds, and the extra rule holds the corruption caused (readings lost with the journal).
"""
import json
import sys
from collections import Counter


def load(path):
    return {json.loads(line)['id']: json.loads(line) for line in open(path)}


def main():
    corpus, plain, bad = (load(p) for p in sys.argv[1:4])
    c = Counter()
    for sid, session in corpus.items():
        mid = len(session['events']) // 2
        after = [r for r in bad[sid]['rows'] if r['i'] > mid]
        base = [r for r in plain[sid]['rows'] if r['i'] > mid]
        c['events_after'] += len(session['events']) - mid - 1
        c['error_blocks'] += sum(r['kind'] == 'error' and r['blocked'] for r in after)
        c['error_reports'] += sum(r['kind'] == 'error' and not r['blocked'] for r in after)
        c['holds'] += sum(r['kind'] == 'hold' for r in after)
        c['holds_uncorrupted'] += sum(r['kind'] == 'hold' for r in base)
        c['sessions'] += 1
        c['sessions_with_error_block'] += any(r['kind'] == 'error' and r['blocked'] for r in after)
    c['extra_holds'] = c['holds'] - c['holds_uncorrupted']
    print(json.dumps(c, indent=1))


if __name__ == '__main__':
    main()
