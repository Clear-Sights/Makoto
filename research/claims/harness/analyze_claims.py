"""Analysis of the claims round, as research/claims/RULES.md fixes it. Committed before any live result.

    python3 -I analyze_claims.py RAW_DIR...

Per family in each RAW_DIR: pass = grade.py exit 0; exact two-sided McNemar; task bootstrap (10,000 resamples,
random.Random(44), percentile 95 %) for the pass difference and the cost ratio; from makoto's streams, holds and notes per
run, and the runs where a note or hold names report.py or a .json file (B2). Supported: makoto passes more than plain with
p < 0.05, or plain passes over 90 % and makoto loses at most 2. Not supported: makoto passes fewer than plain minus 4.
"""
import gzip, json, math, random, re, statistics, sys
from pathlib import Path

out = {}
for raw in map(Path, sys.argv[1:]):
    res = {}
    for p in sorted((raw / 'results').glob('*.json')):
        r = json.loads(p.read_text()); res.setdefault((r['mech'], r['arm']), {})[r['seed']] = r
    for fam in sorted({k[0] for k in res}):
        P, M = res.get((fam, 'plain'), {}), res.get((fam, 'makoto'), {})
        keep = sorted(s for s in P if s in M and P[s]['usable'] and M[s]['usable'])
        pa, pb = [bool(P[s]['passed']) for s in keep], [bool(M[s]['passed']) for s in keep]
        x, y = sum(a and not b for a, b in zip(pa, pb)), sum(b and not a for a, b in zip(pa, pb)); n = x + y
        p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(x, y) + 1)) / 2 ** n)

        def boot(va, vb, kind):
            rnd, k, o = random.Random(44), len(va), []
            for _ in range(10000):
                idx = [rnd.randrange(k) for _ in range(k)]
                ma, mb = sum(va[i] for i in idx) / k, sum(vb[i] for i in idx) / k
                o.append(mb - ma if kind == 'diff' else (mb / ma if ma else float('nan')))
            o = sorted(v for v in o if v == v)
            return [round(o[int(0.025 * len(o))], 3), round(o[int(0.975 * len(o)) - 1], 3)]
        holds = notes = named = 0
        for s in keep:
            r = M[s]; path = raw / 'streams' / f"makoto_{fam}_{s}{'' if r['attempt'] == 1 else '_retry'}.jsonl.gz"
            hit = False
            for line in gzip.open(path, 'rt'):
                if not line.startswith('{'):
                    continue
                e = json.loads(line)
                if e.get('type') == 'system' and e.get('subtype') == 'hook_response':
                    o = e.get('stdout') or ''
                    holds += '"decision": "block"' in o; notes += 'additionalContext' in o
                    hit = hit or bool(('"decision": "block"' in o or 'additionalContext' in o) and re.search(r'report\.py|\.json', o))
            named += hit
        ca, cb = [P[s]['cost_usd'] for s in keep], [M[s]['cost_usd'] for s in keep]
        k = len(keep)
        verdict = ('supported' if (sum(pb) > sum(pa) and p < 0.05) or (sum(pa) > 0.9 * k and sum(pb) >= sum(pa) - 2)
                   else 'not supported' if sum(pb) < sum(pa) - 4 else 'undecided')
        out[f'{raw.name}/{fam}'] = {
            'n': k, 'models': sorted({m for s in keep for m in P[s]['models'] + M[s]['models']}), 'pass_plain': sum(pa), 'pass_makoto': sum(pb),
            'discordant': [x, y], 'p': round(p, 4), 'diff_points': round(100 * (sum(pb) - sum(pa)) / k, 1), 'diff_95': [round(100 * v, 1) for v in boot(list(map(int, pa)), list(map(int, pb)), 'diff')],
            'mean_cost_plain': round(statistics.mean(ca), 5), 'cost_ratio': round(statistics.mean(cb) / statistics.mean(ca), 3), 'cost_95': boot(ca, cb, 'ratio'),
            'mean_seconds': [round(statistics.mean(P[s]['seconds'] for s in keep), 1), round(statistics.mean(M[s]['seconds'] for s in keep), 1)],
            'makoto_holds_per_run': round(holds / k, 3), 'makoto_notes_per_run': round(notes / k, 3), 'makoto_runs_naming_report_or_json': named, 'verdict': verdict}
print(json.dumps(out, indent=1))
