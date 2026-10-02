"""Measure declarative zero separately from current implementation evidence.

Reads only mesh/, PLAN.md, TASKS.tsv and MESH.tsv. Outside receipt pins are
EXTERNAL, never silently trusted. Run again whenever selected inputs change.
"""
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = 'mesh/evidence/zero.json'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def allowed(name):
    if not isinstance(name, str):
        return False
    path = PurePosixPath(name)
    return (str(path) == name and not path.is_absolute()
            and '..' not in path.parts
            and (name in {'PLAN.md', 'TASKS.tsv', 'MESH.tsv'}
                 or name.startswith('mesh/')))


def table(data):
    return list(csv.DictReader(data.decode('utf-8').splitlines(), delimiter='\t'))


def measure(root):
    names = {'PLAN.md', 'TASKS.tsv', 'MESH.tsv'}
    names.update(p.relative_to(root).as_posix() for p in (root/'mesh').rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts
                 and p.suffix != '.pyc')
    names.discard(OUTPUT)
    # Resolve before reading so a symlink cannot extend the authorized scope.
    files = {}
    for name in sorted(names):
        path = root/name
        resolved = path.resolve()
        if path.is_file() and (resolved == path.absolute()):
            files[name] = path.read_bytes()
    return files, sorted(names-files.keys())


def receipt_state(receipt, files):
    if not isinstance(receipt, dict):
        receipt = {}
    pins = receipt.get('source_pins')
    valid = (isinstance(pins, dict) and bool(pins)
             and all(isinstance(n, str) and isinstance(h, str)
                     and len(h) == 64 and all(c in '0123456789abcdef' for c in h)
                     for n, h in pins.items()))
    pins = pins if valid else {}
    outside = sorted(n for n in pins if not allowed(n) or n == OUTPUT)
    missing = sorted(n for n in pins if n not in outside and n not in files)
    stale = sorted(n for n, h in pins.items()
                   if n in files and sha(files[n]) != h)
    digest_valid = bool(valid and sha(canonical(pins)) == receipt.get('selected_input_digest'))
    current = digest_valid and not outside and not missing and not stale
    observations = receipt.get('observations', [])
    observed = (isinstance(observations, list) and bool(observations)
                and all(isinstance(o, dict) and o.get('result') == 'pass'
                        for o in observations)
                and any(o.get('synthetic') is not True for o in observations))
    accepted = bool(current and observed and receipt.get('result') == 'pass'
                    and not receipt.get('absent') and not receipt.get('external')
                    and receipt.get('status') not in ('EXTERNAL', 'OPEN', 'PARTIAL', 'CANDIDATE')
                    and receipt.get('done') is not False
                    and receipt.get('decision') != 'not_done')
    return dict(current=bool(current), accepted=accepted, digest_valid=digest_valid,
                outside_evidence=outside, missing_inputs=missing, stale_inputs=stale)


def derive_waves(tasks):
    remaining = {t['task']: t for t in tasks}
    if len(remaining) != len(tasks):
        raise ValueError('duplicate task')
    waves, finished = [], set()
    while remaining:
        ready = sorted(n for n, t in remaining.items()
                       if set(filter(None, t['deps'].split(','))) <= finished)
        if not ready:
            raise ValueError('missing dependency or cycle: re-measure and re-derive')
        waves.append(dict(wave=len(waves)+1, tasks=ready,
                          predicted_tokens=sum(int(remaining[n]['estimate_tokens']) for n in ready)))
        finished.update(ready)
        for n in ready:
            del remaining[n]
    return waves


def contracts(files):
    constraints = table(files['mesh/CONSTRAINTS.tsv'])
    relations = []
    for req in table(files['mesh/REQUIREMENTS.tsv']):
        accepted = set(json.loads(req['universe']))
        for c in constraints:
            if c['requirement'] == req['requirement']:
                accepted &= set(json.loads(c['accepts']))
        relations.append(dict(requirement=req['requirement'], accepted=sorted(accepted),
                              missing=sorted(accepted-set(json.loads(req['allowed']))),
                              over=sorted(set(json.loads(req['required']))-accepted)))
    return relations


def implementation(receipts, files, slots):
    states, absent, external = {}, [], []
    for slot in slots:
        name = slot['slot']
        if name in ('PROGRAM_INPUT', 'PROGRAM_OUTPUT'):
            continue
        receipt = receipts.get(name, {})
        state = receipt_state(receipt, files)
        requirements = receipt.get('requirements')
        identity = (isinstance(requirements, list)
                    and all(isinstance(r, str) for r in requirements)
                    and receipt.get('task') == name
                    and set(filter(None, slot['requirements'].split(',')))
                    <= set(requirements))
        state['accepted'] = state['accepted'] and identity
        states[name] = state
        if not state['accepted']:
            absent.append(name+':current_passing_evidence')
        if slot['fill-status'] == 'OPEN' or not slot['filled-by']:
            absent.append(name+':bound_proof_producer')
        external.extend(state['outside_evidence'])
        external.extend(str(e) for e in receipt.get('external', []))
    join = receipts.get('join', {})
    verdict = join.get('verdict')
    if (join.get('decision') != 'done' or not isinstance(verdict, dict)
            or verdict.get('decision') != 'done'):
        absent.append('join:current_done_verdict')
    return states, sorted(set(absent)), sorted(set(external))


def main():
    files, missing = measure(ROOT)
    pins = {n: sha(data) for n, data in files.items()}
    waves = derive_waves(table(files['TASKS.tsv']))
    plan = files['PLAN.md'].decode('utf-8')
    plan_matches = all(f"Wave {w['wave']}: {', '.join(w['tasks'])} (predicted {w['predicted_tokens']} tokens)"
                       in plan for w in waves)
    relations = contracts(files)
    receipts, invalid = {}, []
    for n, data in files.items():
        if n.startswith('mesh/evidence/') and n.endswith('.json'):
            try:
                r = json.loads(data)
                if not isinstance(r, dict):
                    raise ValueError('receipt is not a record')
                receipts[Path(n).stem] = r
            except ValueError:
                invalid.append(n)
    states, absent, external = implementation(receipts, files, table(files['mesh/SLOTS.tsv']))
    check = subprocess.run(['python3', 'mesh/check.py', '--task', 'zero'], cwd=ROOT,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                           capture_output=True, text=True)
    model_zero = (check.returncode == 0 and plan_matches and not missing
                  and all(not r['missing'] and not r['over'] for r in relations))
    after, missing_after = measure(ROOT)
    stable = files == after and missing == missing_after
    if not stable:
        absent.append('zero:input_changed_during_measurement')
    absent.extend(n+':missing_input' for n in missing)
    absent.extend(n+':invalid_evidence' for n in invalid)
    done = bool(model_zero and stable and not absent and not external and states)
    report = dict(task='zero', selected_input_digest=sha(canonical(pins)), source_pins=pins,
                  digest_method='SHA-256 of canonical source_pins JSON; sorted keys, compact separators, UTF-8, ensure_ascii=False; zero output excluded',
                  model=dict(zero=model_zero,
                             missing=sum(len(r['missing']) for r in relations),
                             over=sum(len(r['over']) for r in relations),
                             structural_violations=sum(line.startswith('  ') for line in check.stdout.splitlines()),
                             relations=relations, plan_matches=plan_matches,
                             check_exit_code=check.returncode, stdout=check.stdout, stderr=check.stderr),
                  dependency_receipts=states, derived_waves=waves, stable_inputs=stable,
                  present=['model:requirement_envelopes'] if model_zero else [],
                  absent=sorted(set(absent)), external=external,
                  done=done, decision='done' if done else 'not_done',
                  result='pass' if done else 'absent',
                  status='EXTERNAL' if external else ('DONE' if done else 'OPEN'),
                  failure_edge='Re-measure changed input and re-derive waves; unavailable operator or outside evidence = EXTERNAL.',
                  reproduction='PYTHONDONTWRITEBYTECODE=1 python3 mesh/zero.py',
                  scope='Only allowed input bytes measured; external pins remain unverified. Model checks do not certify runtime completion.')
    (ROOT/OUTPUT).write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(dict(model_zero=model_zero, done=done, status=report['status'], waves=len(waves))))
    return 0 if model_zero and stable else 1


if __name__ == '__main__':
    raise SystemExit(main())
