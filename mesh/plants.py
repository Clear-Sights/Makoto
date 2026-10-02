"""One hostile mutation per computed check, in minimal credential-free copies.
No runtime imports, hooks, test suite, gate, network or checkout mutations.
--copy TASK prints a private copy whose MESH check must fail, for route Step 0.
"""
from pathlib import Path
import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ('schema','wires','reachable','trace','coverage','fills','missing','over','subtractions','route','wire-rule','tighten')
COPY_PATHS = ('mesh','WORDS.tsv','SPIRIT.md','PLAN.md','TASKS.tsv','MESH.tsv','plugin/makoto2','tests')


def read(path):
    with path.open(newline='') as f:
        r=csv.DictReader(f,delimiter='\t');return r.fieldnames,list(r)


def write(path,fields,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)


def mutate(copy,check):
    filename={'schema':'SOURCES','wires':'WIRES','reachable':'WIRES','trace':'SLOTS','coverage':'REQUIREMENTS','fills':'FILLS','missing':'CONSTRAINTS','over':'CONSTRAINTS','subtractions':'SUBTRACT','route':None,'wire-rule':'WIRES','tighten':'TIGHTEN'}[check]
    path=copy/'mesh'/(filename+'.tsv') if filename else copy/'TASKS.tsv'
    fields,rows=read(path)
    if check=='tighten':rows[-1]['shape']='{}'
    elif check=='wire-rule':rows.append(dict(wire='plant-identity',source='PROGRAM_INPUT#raw',target='decode#raw',requirements='decode'))
    elif check=='schema':rows[0]['sha256']='0'*64
    elif check=='wires':rows[0]['target']='configure#defaults'
    elif check=='reachable':rows=[w for w in rows if not (w['source'].startswith('decode#') or w['target'].startswith('decode#'))]
    elif check=='trace':next(s for s in rows if s['slot']=='once')['requirements']=''
    elif check=='coverage':rows[0]['port']='absent'
    elif check=='fills':rows[0]['unit']='no_such_function'
    elif check=='missing':rows=[c for c in rows if c['requirement']!='detect']
    elif check=='over':rows[0]['accepts']='[]'
    elif check=='subtractions':rows[0]['reason']=''
    elif check=='route':next(t for t in rows if t['task']=='zero')['deps']='zero'
    write(path,fields,rows)


def local_copy():
    dest=Path(tempfile.mkdtemp(prefix='makoto-topdown-'))
    for relative in COPY_PATHS:
        src=ROOT/relative;target=dest/relative
        if src.is_dir():shutil.copytree(src,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        else:target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    return dest


def command(copy,check=None,task=None):
    args=[sys.executable,str(copy/'mesh/check.py')]
    if check:args+=['--only',check]
    if task:args+=['--task',task]
    return subprocess.run(args,cwd=copy,text=True,capture_output=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('check',nargs='?',choices=CHECKS);parser.add_argument('--copy',metavar='TASK');args=parser.parse_args()
    if args.copy:
        _,tasks=read(ROOT/'TASKS.tsv')
        if args.copy not in {t['task'] for t in tasks}:parser.error('unknown task')
        copy=local_copy();mutate(copy,'missing');print(copy);return 0
    selected=(args.check,) if args.check else CHECKS
    failures=[]
    for check in selected:
        copy=local_copy()
        try:
            baseline=command(copy,check)
            mutate(copy,check)
            result=command(copy,check)
            expected=check+': FAIL'
            ok=baseline.returncode==0 and result.returncode!=0 and expected in result.stdout
            print(check+': '+('plant RED (baseline PASS)' if ok else 'plant FAILED'))
            if not ok:failures.append(check);print(baseline.stdout+result.stdout+result.stderr)
        finally:shutil.rmtree(copy)
    return int(bool(failures))

if __name__=='__main__':raise SystemExit(main())
