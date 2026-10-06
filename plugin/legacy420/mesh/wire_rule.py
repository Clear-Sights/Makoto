"""Classify declared data flow, without inspecting candidate implementation.
input-sources is authoritative even when a wire is deleted. output-from declares
which inputs a function transforms; an output alias (string) is identity/local.
"""
from pathlib import Path
import argparse
import csv
import io
import json

MESH = Path(__file__).resolve().parent
FIELDS = ('wire or pair', 'verdict', 'reason')


def read(mesh, name):
    with (mesh / (name + '.tsv')).open() as f:
        return list(csv.DictReader(f, delimiter='\t'))


def classify(mesh=MESH):
    slots = {s['slot']: s for s in read(mesh, 'SLOTS')}
    wires = read(mesh, 'WIRES')
    def verdict(source, target):
        a, p = source.split('#'); b, q = target.split('#')
        if a == b:
            return 'FOLD', 'local I/O inside one slot'
        left = slots[a]; right = slots[b]
        if left['filled-by'] and left['filled-by'] == right['filled-by']:
            return 'FOLD', 'both ends inside one function fill'
        origin = json.loads(left['output-from']).get(p)
        if not isinstance(origin, list) or not origin:
            return 'FOLD', 'identity input or direct variable binding; no transformation'
        if not set(origin) <= json.loads(left['inputs']).keys():
            raise ValueError('unknown transformation input ' + source)
        if json.loads(right['input-sources']).get(q) != source:
            return 'FOLD', 'not a declared transformed input dependency'
        return 'KEEP', 'transformed input crosses distinct slots'
    rows = []
    pairs = set()
    for w in wires:
        pair = (w['source'], w['target']); pairs.add(pair)
        v, reason = verdict(*pair)
        rows.append(dict(zip(FIELDS, (w['wire'], v, reason))))
    for b, s in slots.items():
        sources = json.loads(s['input-sources'])
        if set(sources) != json.loads(s['inputs']).keys():
            raise ValueError('incomplete input provenance ' + b)
        for q, source in sorted(sources.items()):
            target = b + '#' + q
            v, reason = verdict(source, target)
            if v == 'KEEP' and (source, target) not in pairs:
                rows.append(dict(zip(FIELDS, (source + ' -> ' + target, 'ADD', reason))))
    return rows


def render(rows):
    out = io.StringIO(); w = csv.DictWriter(out, FIELDS, delimiter='\t', lineterminator='\n')
    w.writeheader(); w.writerows(rows); return out.getvalue()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--apply', action='store_true'); args = parser.parse_args()
    rows = classify()
    (MESH / 'WIRE-RULE.tsv').write_text(render(rows))
    if args.apply:
        wires = read(MESH, 'WIRES'); slots = {s['slot']: s for s in read(MESH, 'SLOTS')}
        folded = {r[FIELDS[0]] for r in rows if r['verdict'] == 'FOLD'}
        wires = [w for w in wires if w['wire'] not in folded]
        for r in rows:
            if r['verdict'] != 'ADD': continue
            source, target = r[FIELDS[0]].split(' -> ')
            b = target.split('#')[0]; a = source.split('#')[0]
            wires.append(dict(wire='add-' + str(len(wires)+1), source=source, target=target,
                              requirements=slots[a if b == 'PROGRAM_OUTPUT' else b]['requirements']))
        with (MESH / 'WIRES.tsv').open('w') as f:
            w = csv.DictWriter(f, ('wire','source','target','requirements'), delimiter='\t', lineterminator='\n')
            w.writeheader(); w.writerows(wires)
    else:
        print(render(rows), end='')
    return 0

if __name__ == '__main__': raise SystemExit(main())
