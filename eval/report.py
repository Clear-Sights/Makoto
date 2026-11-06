"""Label every hold of a results file with eval/label.py and print the counts.

    python3 eval/report.py corpus.jsonl results.jsonl [--show N]
"""
import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import label as oracle  # noqa: E402


def load(path):
    return {json.loads(line)['id']: json.loads(line) for line in open(path)}


def tally(corpus, results):
    steps = collections.Counter()      # hold steps (a step can carry several findings)
    findings = collections.Counter()   # (rule, label)
    notes = collections.Counter()
    fp_examples, errors, retries = [], 0, collections.Counter()
    for sid, result in results.items():
        events = corpus[sid]['events']
        for row in result['rows']:
            if row['kind'] == 'error':
                errors += 1
            elif row['kind'] == 'retry':
                retries[(row['n'], row['result'])] += 1
            elif row['kind'] == 'hold':
                found = oracle.findings(row['reason'])
                if not found:
                    findings[('contract', 'true')] += 1
                    steps['hold'] += 1
                    continue
                steps['hold'] += 1
                labels = []
                for rule, subject in found:
                    lab, note = oracle.label(events, row['i'], rule, subject)
                    findings[(rule, lab)] += 1
                    notes[(rule, lab, note.split(' by ')[0])] += 1
                    labels.append(lab)
                    if lab == 'fp':
                        fp_examples.append((sid, row['i'], rule, subject, note))
                steps['fp_step'] += all(x == 'fp' for x in labels)
                steps['part_fp_step'] += any(x == 'fp' for x in labels) and not all(x == 'fp' for x in labels)
    return steps, findings, notes, fp_examples, errors, retries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('corpus')
    ap.add_argument('results')
    ap.add_argument('--show', type=int, default=0)
    args = ap.parse_args()
    corpus = load(args.corpus)
    steps, findings, notes, fp_examples, errors, retries = tally(corpus, load(args.results))
    out = {'sessions': len(corpus), 'hold_steps': steps['hold'], 'steps_all_findings_fp': steps['fp_step'],
           'steps_some_findings_fp': steps['part_fp_step'], 'errors': errors,
           'findings': {f'{r}/{l}': n for (r, l), n in sorted(findings.items())},
           'notes': {'/'.join(k): n for k, n in sorted(notes.items()) if k[2]},
           'retries': {f'{n}/{r}': c for (n, r), c in sorted(retries.items())}}
    print(json.dumps(out, indent=1))
    for example in fp_examples[:args.show]:
        print(example)


if __name__ == '__main__':
    main()
