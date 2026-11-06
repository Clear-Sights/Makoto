"""All figures of eval/RULES3.md for one run.

    python3 eval/summarize.py DIR RUN [seed]

DIR holds corpus3.jsonl, plants3.jsonl, plants23.jsonl and the result files res3_<RUN>.jsonl, pl3_<RUN>.jsonl,
pl23_<RUN>.jsonl, clear3_<RUN>.jsonl written by eval/run_corpus.py.
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare  # noqa: E402
import independent  # noqa: E402
from stats import show  # noqa: E402

DEPENDENT = 2718


def plants_row(plants, results):
    n, caught = Counter(), Counter()
    for pid, plant in plants.items():
        kind = plant['plant']
        n[kind] += 1
        if any(r['kind'] == 'hold' and r['i'] == plant['step'] for r in results[pid]['rows']):
            caught[kind] += 1
    return n, caught


def main():
    d, run = Path(sys.argv[1]), sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 20261107
    corpus = compare.load(d / 'corpus3.jsonl')
    results = compare.load(d / f'res3_{run}.jsonl')
    c = compare.corpus_row(corpus, results)
    out = {'run': run, 'holds': c['holds'], 'hold_rate': show(c['holds'], DEPENDENT), 'errors': c['errors'],
           'fp_holds_label_py': show(c['fp_holds'], c['holds']), 'fp_findings_label_py': f"{c['fp_findings']}/{c['findings']}"}
    holds = sorted(({'id': sid, 'i': r['i'], 'reason': r['reason']} for sid, res in results.items() for r in res['rows'] if r['kind'] == 'hold'),
                   key=lambda h: (h['id'], h['i']))
    sample = random.Random(seed).sample(holds, 60)
    fps, present, total, by_rule, causes = 0, 0, 0, Counter(), Counter()
    for h in sample:
        verdicts = independent.judge(corpus[h['id']]['events'], h['i'], h['reason'])
        fps += bool(verdicts) and all(p for _, _, p in verdicts)
        for rule, subject, p in verdicts:
            total += 1
            present += p
            by_rule[rule, p] += 1
            if p:
                causes[rule] += 1
    # Added after tracing the first R2 sample (not in RULES3.md): the replay keeps calls Makoto denied, but a live
    # session would not have run them, so text produced only by a denied call is not evidence. Same sample, same labeler,
    # counting only the calls that ran.
    ran_present = ran_total = 0
    for h in sample:
        events = corpus[h['id']]['events']
        dead = {events[r['i']]['tool_use_id'] for r in results[h['id']]['rows'] if r['kind'] == 'hold' and events[r['i']]['hook_event_name'] == 'PreToolUse'}
        live = [e for e in events[:h['i']] if e.get('tool_use_id') not in dead]
        for rule, subject in independent.findings(h['reason']):
            ran_total += 1
            ran_present += independent.present(live, len(live), rule, subject)
    out['misdirected_counting_only_calls_that_ran'] = show(ran_present, ran_total)
    out['sample_seed'] = seed
    out['independent_fp'] = show(fps, 60)
    out['misdirected_findings'] = show(present, total)
    out['misdirected_by_rule'] = {r: f"{by_rule[r, True]}/{by_rule[r, True] + by_rule[r, False]}" for r in sorted({k[0] for k in by_rule})}
    for name, plants_file, results_file in (('first_round', 'plants3', 'pl3'), ('round_two', 'plants23', 'pl23')):
        plants = compare.load(d / f'{plants_file}.jsonl')
        n, caught = plants_row(plants, compare.load(d / f'{results_file}_{run}.jsonl'))
        out[name] = {k: show(caught[k], n[k]) for k in sorted(n)}
        out[name]['all'] = show(sum(caught.values()), sum(n.values()))
    clear = [r for line in open(d / f'clear3_{run}.jsonl') for r in json.loads(line)['rows'] if r['kind'] == 'clear']
    out['stops_cleared_by_named_action'] = f"{sum(r['result'] == 'ok' for r in clear)}/{len(clear)}"
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
