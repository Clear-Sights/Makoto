"""Least finite slot shapes by descending fixpoint; no model in the loop.

Countdown kernel.ml Wire.subtract (top-level extracted subtract) uses heldb
support over candidate assignments, users and table dictionaries. This model
has independent behavioral facets, no candidate/support relation to supply.
Adapting that kernel would invent structure. Use finite set subtraction here.
Nominal carriers are invariant (check.py); facets on a shared port are separate
partitions, so never intersect labels belonging to different requirements.
"""
from pathlib import Path
import csv
import io
import json

MESH = Path(__file__).resolve().parent
FIELDS = ('step', 'slot', 'shape', 'removed', 'fixpoint')


def read(mesh, name):
    with (mesh / (name + '.tsv')).open() as f:
        return list(csv.DictReader(f, delimiter='\t'))


def derive(mesh=MESH):
    slots = read(mesh, 'SLOTS'); requirements = read(mesh, 'REQUIREMENTS')
    constraints = read(mesh, 'CONSTRAINTS')
    state = {r['requirement']: set(json.loads(r['universe'])) for r in requirements}
    least = {}
    for r in requirements:
        key = r['requirement']; allowed = set(json.loads(r['allowed']))
        required = set(json.loads(r['required'])); accepted = set(state[key])
        for c in constraints:
            if c['requirement'] == key:
                accepted &= set(json.loads(c['accepts']))
        if not required or not required <= accepted <= allowed <= state[key]:
            raise ValueError('requirement does not pass: ' + key)
        # Every required case must remain; every other case can be removed.
        least[key] = required
    rows = []; step = 0; removed = {k: 0 for k in state}
    while True:
        following = {k: values & least[k] for k, values in state.items()}
        fixed = following == state
        for s in slots:
            refs = [r['requirement'] for r in requirements if r['slot'] == s['slot']]
            shape = dict(inputs=json.loads(s['inputs']), outputs=json.loads(s['outputs']),
                         relations={k: sorted(state[k]) for k in refs})
            rows.append(dict(step=str(step), slot=s['slot'],
                             shape=json.dumps(shape, sort_keys=True, separators=(',', ':')),
                             removed=str(sum(removed[k] for k in refs)),
                             fixpoint='yes' if fixed else 'no'))
        if fixed:
            return rows, step
        removed = {k: len(state[k] - following[k]) for k in state}
        state = following; step += 1


def render(mesh=MESH):
    rows, _ = derive(mesh)
    out = io.StringIO(); w = csv.DictWriter(out, FIELDS, delimiter='\t', lineterminator='\n')
    w.writeheader(); w.writerows(rows); return out.getvalue()

if __name__ == '__main__':
    (MESH / 'TIGHTEN.tsv').write_text(render())
    print('tighten fixpoint after', derive()[1], 'steps')
