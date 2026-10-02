"""Deterministic structural proof checker; unresolved proofs cannot exit zero."""
import sys
if __name__ == '__main__':
    sys.path.pop(0)
import csv
import hashlib
import subprocess
import json
import sys
from pathlib import Path
import types as stdlib_types

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ('inventory', 'types', 'wires', 'reachable', 'fills', 'coverage', 'missing', 'over', 'package', 'installed-fresh', 'whole-repo-clean')
INPUT = 'PROGRAM_INPUT'
OUTPUT = 'PROGRAM_OUTPUT'
FORBIDDEN = ('UNRESOLVED', 'Any')

# Load the sibling extractor without shadowing Python's stdlib types module.
def extractor():
    module = stdlib_types.ModuleType('mesh_extractor')
    module.__file__ = str(ROOT/'mesh/types.py')
    exec(compile((ROOT/'mesh/types.py').read_text(), module.__file__, 'exec'), module.__dict__)
    return module

def read(name):
    with (ROOT/'mesh'/name).open() as f:
        return list(csv.DictReader(f, delimiter='\t'))

def measure():
    errors = {k: [] for k in CHECKS}
    rows = read('SLOTS.tsv'); wires = read('WIRES.tsv'); requirements = read('REQUIREMENTS.tsv')
    slots = {r['slot']: r for r in rows}
    for s in rows:
        for field in ('inputs:type','outputs:type'):
            s[field] = json.loads(s[field])
    expected, ew = extractor().extract(ROOT)
    if rows != expected or wires != ew: errors['inventory'].append('AST inventory or call argument/return wiring differs')
    for s in rows:
        for direction in ('inputs:type','outputs:type'):
            for port, typ in s[direction].items():
                if any(x in typ for x in FORBIDDEN): errors['types'].append(s['slot']+'#'+port)
    graph = {k:set() for k in slots}; reverse = {k:set() for k in slots}
    for w in wires:
        a, ap = w['from-slot.output'].split('#',1); b,bp = w['to-slot.input'].split('#',1)
        if a not in slots or b not in slots or slots[a]['outputs:type'].get(ap) != w['type'] or slots[b]['inputs:type'].get(bp) != w['type']:
            errors['wires'].append(str(w)); continue
        graph[a].add(b); reverse[b].add(a)
    def reach(g, start):
        seen=set(); pending=[start]
        while pending:
            x=pending.pop()
            if x in seen: continue
            seen.add(x); pending.extend(sorted(g.get(x,())))
        return seen
    forward=reach(graph,INPUT); backward=reach(reverse,OUTPUT)
    errors['reachable'] = sorted(set(slots)-forward | (set(slots)-backward))
    filled=[s['filled-by'] for s in rows if s['filled-by']!='EMPTY']
    if len(filled)!=len(set(filled)): errors['fills'].append('code unit fills multiple slots')
    if len(slots)!=len(rows): errors['inventory'].append('duplicate slot id')
    if len({r['requirement id'] for r in requirements})!=len(requirements): errors['coverage'].append('duplicate requirement id')
    for r in requirements:
        s=slots.get(r['slot']); port=r['port']
        actual = None if s is None else s['inputs:type'].get(port,s['outputs:type'].get(port))
        if actual is None: errors['coverage'].append(r['requirement id'])
        required=set(json.loads(r['required'])); allowed=set(json.loads(r['allowed']))
        # Actual accepted domain is a finite, explicit shape contract. Missing domain is unknown.
        domain_path=ROOT/'mesh/DOMAINS.tsv'
        domains={d['slot']+'#'+d['port']:set(json.loads(d['values'])) for d in read('DOMAINS.tsv')}
        domain=domains.get(r['slot']+'#'+port)
        if domain is not None:
            import ast
            try:
                shape=ast.parse(actual or '',mode='eval').body
                items=shape.slice.elts if isinstance(shape.slice,ast.Tuple) else [shape.slice]
                proven={ast.literal_eval(x) for x in items} if isinstance(shape,ast.Subscript) and ast.unparse(shape.value)=='Literal' else None
            except (SyntaxError,ValueError,AttributeError,TypeError): proven=None
            if proven!=domain: errors['missing'].append(r['requirement id']+': domain not established by source type')
        if domain is None: errors['missing'].append(r['requirement id']+': no proven domain')
        else:
            if domain-allowed: errors['missing'].append(r['requirement id']+': '+repr(sorted(domain-allowed)))
            if required-domain: errors['over'].append(r['requirement id']+': '+repr(sorted(required-domain)))
    manifest=json.loads((ROOT/'plugin/.claude-plugin/plugin.json').read_text())
    market=json.loads((ROOT/'.claude-plugin/marketplace.json').read_text())
    if (ROOT/'README.md').read_text().splitlines()[0]!='# Makoto '+manifest['version'] or market['plugins'][0]['source']!='./plugin':
        errors['package'].append('manifest/readme/marketplace disagree')
    for kind in ('installed-fresh','whole-repo-clean'):
        receipt=ROOT/'mesh'/('RECEIPT-'+kind+'.json')
        if not receipt.exists(): errors[kind].append('EXTERNAL: evidence absent')
        else:
            data=json.loads(receipt.read_text())
            current={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.glob('plugin/**/*')) if p.is_file()}
            if data.get('inputs') != current: errors[kind].append('receipt inputs differ')
            if kind=='installed-fresh':
                if data.get('version')!=manifest['version'] or data.get('fresh') is not True or data.get('slip')!='blocked' or data.get('control')!='silent' or data.get('runtime_errors')!=[] or not data.get('provenance'): errors[kind].append('fresh session observations incomplete')
            else:
                status=subprocess.run(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT,capture_output=True,text=True)
                whitespace=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True,text=True)
                if status.returncode or status.stdout or whitespace.returncode or data.get('audited')!=current: errors[kind].append('whole repo audit or clean worktree absent')
    return errors,rows,wires

def main():
    errors,slots,wires=measure()
    selected=sys.argv[2] if len(sys.argv)==3 and sys.argv[1]=='--only' else None
    if len(sys.argv)==3 and sys.argv[1]=='--component':
        components={r['task']:set(json.loads(r['slots'])) for r in read('COMPONENTS.tsv')}
        members=components[sys.argv[2]]
        requirements={r['requirement id'] for r in read('REQUIREMENTS.tsv') if r['slot'] in members}
        errors={k:[v for v in values if k in ('inventory','fills') or any(v==s or v.startswith(s+'#') or ('"'+s+'#') in v or ("'"+s+'#') in v for s in members) or any(v.startswith(r+':') or v==r for r in requirements)] for k,values in errors.items()}
    if selected is not None and selected not in CHECKS:
        print('unknown check: '+selected)
        return 2
    for kind, failures in errors.items():
        if selected and selected!=kind: continue
        label={'missing':'MISSING-CONSTRAINT','over':'OVER-CONSTRAINT'}.get(kind,kind)
        print(label+': '+str(len(failures)))
        for failure in failures[:5]: print('  '+failure)
    return int(any(v for k,v in errors.items() if selected is None or k==selected))

if __name__=='__main__':
    sys.exit(main())
