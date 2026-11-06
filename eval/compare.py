"""Print the corpus-gate table for the variants.

    python3 eval/compare.py DIR     # DIR holds corpus.jsonl, plants.jsonl, res_<v>[_scoped].jsonl, pl_<v>[_scoped].jsonl
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import label as oracle  # noqa: E402


def load(path):
    return {json.loads(line)['id']: json.loads(line) for line in open(path)}


def corpus_row(corpus, results):
    c = Counter()
    for sid, result in results.items():
        events = corpus[sid]['events']
        for row in result['rows']:
            if row['kind'] == 'error':
                c['errors'] += 1
                c['errors_blocked'] += row['blocked']
            elif row['kind'] == 'report':
                c['reports'] += 1
            elif row['kind'] == 'retry':
                c['retries'] += 1
                c['retries_blocked'] += row['blocked']
            elif row['kind'] == 'hold':
                c['holds'] += 1
                c['blocked'] += row['blocked']
                found = oracle.findings(row['reason'])
                labels = [oracle.label(events, row['i'], r, s)[0] for r, s in found]
                c['findings'] += len(labels)
                c['fp_findings'] += labels.count('fp')
                fp_step = bool(labels) and all(x == 'fp' for x in labels)
                c['fp_holds'] += fp_step
                c['fp_blocked'] += fp_step and row['blocked']
    return c


def plant_row(plants, results):
    c = Counter()
    for pid, plant in plants.items():
        c['n_' + plant['plant']] += 1
        rows = results[pid]['rows']
        c['errors'] += sum(r['kind'] == 'error' for r in rows)
        step = [r for r in rows if r['i'] == plant['step']]
        if any(r['kind'] == 'hold' for r in step):
            c['caught_' + plant['plant']] += 1
            c['caught'] += 1
        if any(r['kind'] == 'hold' and r['blocked'] for r in step):
            c['blocked'] += 1
        c['n'] += 1
    return c


def main():
    d = Path(sys.argv[1])
    corpus, plants = load(d / 'corpus.jsonl'), load(d / 'plants.jsonl')
    print('| run | holds | blocked | FP holds | FP findings / findings | errors | stop retries blocked | plants caught / n (P1, P3) | plants blocked | errors on plants |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for name in ('base', 'v1', 'v2', 'v3', 'all', 'base_scoped', 'v1_scoped', 'all_scoped'):
        if not (d / f'res_{name}.jsonl').exists():
            continue
        c = corpus_row(corpus, load(d / f'res_{name}.jsonl'))
        p = plant_row(plants, load(d / f'pl_{name}.jsonl'))
        print(f"| {name} | {c['holds']} | {c['blocked']} | {c['fp_holds']} | {c['fp_findings']} / {c['findings']} | {c['errors']} "
              f"| {c['retries_blocked']} / {c['retries']} | {p['caught']} / {p['n']} (P1 {p['caught_P1']}/{p['n_P1']}, P3 {p['caught_P3']}/{p['n_P3']}) "
              f"| {p['blocked']} | {p['errors']} |")


if __name__ == '__main__':
    main()
