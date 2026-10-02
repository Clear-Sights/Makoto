"""Hostile plants in disposable copies. A failing baseline is not plant proof.
Each plant must introduce a new diagnostic for its selected check.
"""
import sys
if __name__ == '__main__':
    sys.path.pop(0)
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ('inventory','types','wires','reachable','fills','coverage','missing','over','package','installed-fresh','whole-repo-clean')

def table(root,name,mutate):
    p=root/'mesh'/name
    with p.open() as f:
        reader=csv.DictReader(f,delimiter='\t'); fields=reader.fieldnames; rows=list(reader)
    mutate(rows)
    with p.open('w') as f:
        writer=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');writer.writeheader();writer.writerows(rows)

def plant(root,kind):
    if kind=='inventory':
        with (root/'plugin/makoto2/hook.py').open('a') as f: f.write('\ndef planted_new_unit(x: str) -> str:\n    return x\n')
    elif kind=='types':
        table(root,'SLOTS.tsv',lambda rows: rows[0].update({'outputs:type':'{"start":"Any"}'}))
    elif kind=='wires':
        table(root,'WIRES.tsv',lambda rows: rows[0].update({'type':'str'}))
    elif kind=='reachable':
        table(root,'WIRES.tsv',lambda rows: rows.pop(0))
    elif kind=='fills':
        def duplicate(rows):
            filled=[r for r in rows if r['filled-by']!='EMPTY'];filled[1]['filled-by']=filled[0]['filled-by']
        table(root,'SLOTS.tsv',duplicate)
    elif kind=='coverage':
        table(root,'REQUIREMENTS.tsv',lambda rows: rows[0].update({'port':'planted_nonexistent_port'}))
    elif kind in ('missing','over'):
        with (root/'mesh/DOMAINS.tsv').open('a') as f:
            f.write('hook.d_in\traw\t'+json.dumps(['planted-extra'] if kind=='missing' else [])+'\n')
    elif kind=='package':
        p=root/'plugin/.claude-plugin/plugin.json';data=json.loads(p.read_text());data['version']='planted-wrong-version';p.write_text(json.dumps(data))
    else:
        (root/'mesh'/('RECEIPT-'+kind+'.json')).write_text('{}')

def measure(root):
    code="import runpy; m=runpy.run_path('mesh/check.py'); e,_,_=m['measure'](); import json; print(json.dumps(e,sort_keys=True))"
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    proc=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,capture_output=True,text=True)
    if proc.returncode: raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout)

def main():
    selected=sys.argv[1] if len(sys.argv)>1 else None
    success=True
    kinds=CHECKS
    if selected and selected not in CHECKS:
        with (ROOT/'mesh/COMPONENTS.tsv').open() as f: components={r['task']:json.loads(r['slots']) for r in csv.DictReader(f,delimiter='\t')}
        if selected not in components: raise ValueError('unknown plant '+selected)
        kinds=(selected,)
    for kind in kinds:
        if selected and selected!=kind: continue
        with tempfile.TemporaryDirectory(prefix='makoto-mesh-plant-') as tmp:
            root=Path(tmp)/'repo'
            shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('.git','.agents','.aws','.codex','__pycache__','.pytest_cache'))
            # Git absence in a plant copy is itself measured by the clean check.
            category=kind if kind in CHECKS else 'inventory'
            baseline=measure(root)[category]
            if kind in CHECKS: plant(root,kind)
            else:
                member=components[kind][0]
                def mutate(rows):
                    row=next(r for r in rows if r['slot']==member)
                    row['multiplicity']='planted conflicting multiplicity'
                table(root,'SLOTS.tsv',mutate)
            changed=measure(root)[category]
            introduced=sorted(set(changed)-set(baseline))
            ok=bool(introduced)
            print(kind+': '+('DETECTED' if ok else 'NOT PROVEN')+'; baseline failures='+str(len(baseline))+'; new='+str(len(introduced)))
            success &= ok
    return int(not success)

if __name__=='__main__':
    sys.exit(main())
