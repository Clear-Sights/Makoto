"""Analysis of one model's cells of the testwait round (research/testwait/RULES.md). The arm named 'collect' is the testwait build;
'against_mini' holds it against 6.2.1. Run once per model's RAW_DIR. It is research/collect/harness/analyze_collect.py with the ship
rule replaced by this round's. Committed before any live result.

    python3 -I analyze_testwait.py RAW_DIR
"""
import gzip, json, math, random, re, statistics, sys
from collections import Counter
from pathlib import Path

raw = Path(sys.argv[1])
ARMS, FAMILIES = ('plain', 'v621', 'collect'), ('unrun', 'sigchange')
res = {}
for p in sorted((raw / 'results').glob('*.json')):
    r = json.loads(p.read_text()); res.setdefault((r['mech'], r['arm']), {})[r['seed']] = r


def mcnemar(a, b):
    x = sum(p and not q for p, q in zip(a, b)); y = sum(q and not p for p, q in zip(a, b)); n = x + y
    return x, y, 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(x, y) + 1)) / 2 ** n)


def boot(va, vb, kind):
    rnd, n, out = random.Random(44), len(va), []
    for _ in range(10000):
        idx = [rnd.randrange(n) for _ in range(n)]
        ma, mb = sum(va[i] for i in idx) / n, sum(vb[i] for i in idx) / n
        out.append(mb - ma if kind == 'diff' else (mb / ma if ma else float('nan')))
    out = sorted(v for v in out if v == v)
    return out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]


def stream(arm, r):
    path = raw / 'streams' / f"{arm}_{r['mech']}_{r['seed']}{'' if r['attempt'] == 1 else '_retry'}.jsonl.gz"
    holds = notes = stops = 0
    for line in gzip.open(path, 'rt'):
        if not line.startswith('{'):
            continue
        e = json.loads(line)
        if e.get('type') == 'system' and e.get('subtype') == 'hook_response':
            out = e.get('stdout') or ''
            holds += '"decision": "block"' in out
            notes += 'additionalContext' in out
            stops += e.get('hook_event') == 'Stop'
    return holds, notes, stops


summary = {}
for fam in FAMILIES:
    keep = sorted(set.intersection(*(set(s for s, r in res.get((fam, a), {}).items() if r['usable']) for a in ARMS)))
    R = {a: [res[fam, a][s] for s in keep] for a in ARMS}
    out = {'tasks_kept': len(keep), 'arms': {}, 'against_plain': {}, 'against_mini': {}}
    for a in ARMS:
        facts = [stream(a, r) for r in R[a]]
        out['arms'][a] = {'pass': sum(r['passed'] for r in R[a]), 'mean_cost_usd': round(statistics.mean(r['cost_usd'] for r in R[a]), 5),
                          'mean_seconds': round(statistics.mean(r['seconds'] for r in R[a]), 1),
                          'holds_per_run': round(statistics.mean(f[0] for f in facts), 3), 'notes_per_run': round(statistics.mean(f[1] for f in facts), 3),
                          'final_answers_admitted_first_time': sum(f[0] == 0 for f in facts)}
    ps = {}
    for base, key, arms in (('plain', 'against_plain', ARMS[1:]), ('v621', 'against_mini', ARMS[2:])):
        for a in arms:
            pa, pb = [bool(r['passed']) for r in R[base]], [bool(r['passed']) for r in R[a]]
            x, y, p = mcnemar(pa, pb); lo, hi = boot(list(map(int, pa)), list(map(int, pb)), 'diff')
            ca, cb = [r['cost_usd'] for r in R[base]], [r['cost_usd'] for r in R[a]]
            clo, chi = boot(ca, cb, 'ratio')
            out[key][a] = {'discordant': [x, y], 'p': round(p, 4), 'diff_points': round(100 * (sum(pb) - sum(pa)) / len(keep), 1),
                           'diff_95': [round(100 * lo, 1), round(100 * hi, 1)], 'cost_ratio': round(statistics.mean(cb) / statistics.mean(ca), 3),
                           'cost_95': [round(clo, 3), round(chi, 3)]}
            if base == 'plain':
                ps[a] = p
    alive = True
    for rank, a in enumerate(sorted(ps, key=ps.get)):
        alive = alive and ps[a] < 0.05 / (len(ps) - rank)
        out['against_plain'][a]['holm_rejects'] = alive
    summary[fam] = out


rule = {'pass_ok': True, 'cost_within_005': True, 'cost_within_010': True, 'cost_below_somewhere': False}
for fam in FAMILIES:
    A, P = summary[fam]['arms'], summary[fam]['against_plain']
    gap = P['collect']['cost_ratio'] - P['v621']['cost_ratio']
    rule['pass_ok'] = rule['pass_ok'] and A['collect']['pass'] >= A['v621']['pass'] - 4
    rule['cost_within_005'] = rule['cost_within_005'] and gap <= 0.05
    rule['cost_within_010'] = rule['cost_within_010'] and gap <= 0.10
    rule['cost_below_somewhere'] = rule['cost_below_somewhere'] or gap < 0
summary['ship_rule_parts'] = rule  # RULES.md: Sonnet needs pass_ok, cost_within_005 and cost_below_somewhere; Haiku needs pass_ok and cost_within_010
print(json.dumps(summary, indent=1))
