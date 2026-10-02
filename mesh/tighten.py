"""Known closure at layer 1; monotone signed feedback inside it at layers 2+."""
from pathlib import Path
import csv
import io
import json
import sympy

MESH = Path(__file__).resolve().parent
FIELDS = ('layer', 'step', 'slot', 'shape', 'removed', 'fixpoint', 'math_before', 'math_after', 'directions')


def read(mesh, name):
    with (mesh / (name + '.tsv')).open() as f:
        return list(csv.DictReader(f, delimiter='\t'))


def slot_math(refs, requirements, state):
    # Each finite behavioral relation is a characteristic polynomial on one
    # indicator per case. Distinct facets have independent parameters.
    terms = []
    for key in refs:
        for index, case in enumerate(sorted(json.loads(requirements[key]['universe']))):
            parameter = sympy.Symbol(key.replace('-', '_') + '_' + str(index))
            if case in state[key]:
                terms.append(parameter + parameter - parameter)
    return sympy.simplify(sympy.Add(*terms))


def derive(mesh=MESH):
    slots = read(mesh, 'SLOTS')
    requirements = {r['requirement']: r for r in read(mesh, 'REQUIREMENTS')}
    constraints = read(mesh, 'CONSTRAINTS')
    state = {}; required = {}
    for key, r in requirements.items():
        universe, allowed, need = [set(json.loads(r[k])) for k in ('universe', 'allowed', 'required')]
        accepted = set(universe)
        for c in constraints:
            if c['requirement'] == key:
                accepted &= set(json.loads(c['accepts']))
        if not need or not need <= accepted <= allowed <= universe:
            raise ValueError('requirement does not pass: ' + key)
        # Close only with source-backed definite constraints, never guesses.
        state[key] = accepted
        required[key] = need
    refs = {s['slot']: [k for k, r in requirements.items() if r['slot'] == s['slot']] for s in slots}
    initial_math = {s['slot']: slot_math(refs[s['slot']], requirements, state) for s in slots}
    rows = []; step = 0; removed = {k: 0 for k in state}
    while True:
        # Known signs: deleting surplus decreases excess; deleting a required
        # case increases missing, so that direction is forbidden. Choose the
        # first surplus per facet for deterministic finite progress.
        following = {k: set(v) for k, v in state.items()}
        for key in sorted(state):
            surplus = sorted(state[key] - required[key])
            if surplus: following[key].remove(surplus[0])
        fixed = following == state
        for s in slots:
            id = s['slot']; keys = refs[id]
            shape = dict(inputs=json.loads(s['inputs']), outputs=json.loads(s['outputs']),
                         relations={k: sorted(state[k]) for k in keys})
            rows.append(dict(layer=str(1 if step == 0 else 2), step=str(step), slot=id,
                shape=json.dumps(shape, sort_keys=True, separators=(',', ':')),
                removed=str(sum(removed[k] for k in keys)),
                fixpoint='yes' if fixed and step > 0 else 'no',
                math_before=str(initial_math[id]),
                math_after=str(slot_math(keys, requirements, state)),
                directions='surplus deletion: excess -1; required deletion: missing +1 (forbidden)'))
        # Always measure layer 2, including an already minimal closed space.
        if fixed and step > 0: return rows, step
        removed = {k: len(state[k] - following[k]) for k in state}
        state = following; step += 1


def render(mesh=MESH):
    rows, _ = derive(mesh)
    out = io.StringIO()
    w = csv.DictWriter(out, FIELDS, delimiter='\t', lineterminator='\n')
    w.writeheader(); w.writerows(rows)
    return out.getvalue()


if __name__ == '__main__':
    (MESH / 'TIGHTEN.tsv').write_text(render())
    print('tighten layers 2, fixpoint step', derive()[1])
