"""One hostile mutation per computed check, in minimal credential-free copies.
No runtime imports, hooks, test suite, gate, network or checkout mutations.
--copy TASK mutates the current disposable working tree for route Step 0.
"""
from pathlib import Path
import argparse
import ast
import os
import csv
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ('schema','wires','reachable','trace','coverage','fills','missing','over','subtractions','route','fill-scope','wire-rule','tighten','costs','acceptance','acceptance-scope')
COPY_PATHS = ('REGISTER.md','mesh','WORDS.tsv','SPIRIT.md','PLAN.md','TASKS.tsv','MESH.tsv','plugin','tests','README.md','HANDOFF.md','.claude-plugin','.github')


def read(path):
    with path.open(newline='') as f:
        r=csv.DictReader(f,delimiter='\t');return r.fieldnames,list(r)


def write(path,fields,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)


def mutate(copy,check):
    filename={'schema':'SOURCES','wires':'WIRES','reachable':'WIRES','trace':'TRACE','coverage':'REQUIREMENTS','fills':'FILLS','missing':'CONSTRAINTS','over':'CONSTRAINTS','subtractions':'SUBTRACT','route':None,'fill-scope':None,'wire-rule':'WIRES','tighten':'TIGHTEN','costs':None,'acceptance':None,'acceptance-scope':None}[check]
    path=copy/'mesh'/(filename+'.tsv') if filename else copy/'TASKS.tsv'
    fields,rows=read(path)
    if check=='acceptance':
        (copy/'tests/test_hook.py').write_text('# empty pytest file\n')
    elif check=='acceptance-scope':
        row=next(t for t in rows if t['task']=='package')
        row['inputs']=','.join(p for p in row['inputs'].split(',') if p!='tests/test_hook.py')
    elif check=='fill-scope':
        row=next(t for t in rows if t['task']=='validate')
        row['inputs']=','.join(p for p in row['inputs'].split(',') if p!='mesh/FILLS.tsv')
    elif check=='costs':
        from seed import measured_costs, task_class
        costs, floor = measured_costs(copy/'mesh/COSTS.tsv')
        rows[0]['estimate_tokens']=str(costs.get(task_class(rows[0]['task']), floor)-1)
    elif check=='tighten':rows[-1]['shape']='{}'
    elif check=='wire-rule':rows.append(dict(wire='plant-identity',source='PROGRAM_INPUT#raw',target='decode#raw',requirements='decode'))
    elif check=='schema':rows[0]['sha256']='0'*64
    elif check=='wires':rows[0]['target']='configure#defaults'
    elif check=='reachable':rows=[w for w in rows if not (w['source'].startswith('decode#') or w['target'].startswith('decode#'))]
    elif check=='trace':rows.pop(0)
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


def empty_fill(copy, task):
    """Remove the task's product units, never its acceptance tests or mesh shape."""
    if task == 'subtract':
        shutil.copy2(copy/'mesh/reference/types.py', copy/'mesh/types.py')
        return
    if task == 'zero':
        (copy/'plugin/makoto2/hook.py').write_text('')
        return
    _, fills = read(copy/'mesh/FILLS.tsv')
    grouped = {}
    for row in fills:
        if row['slot'] == task and not row['path'].startswith('tests/'):
            grouped.setdefault(row['path'], set()).add(row['unit'])
    if task == 'validate':
        for name in ('test_hook.py', 'test_evaluate.py', 'test_observed.py'):
            (copy/'tests'/name).unlink(missing_ok=True)
    for name, units in grouped.items():
        path = copy/name
        if '<module>' in units:
            path.write_text('"""Empty product fill plant."""\n')
            continue
        tree = ast.parse(path.read_text())
        lines = path.read_text().splitlines(keepends=True)
        spans = []
        def visit(node, prefix=''):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    unit = prefix + child.name
                    if unit in units:
                        start = min([child.lineno] + [d.lineno for d in getattr(child, 'decorator_list', [])])
                        spans.append((start-1, child.end_lineno))
                    else:
                        visit(child, unit+'.')
                else:
                    visit(child, prefix)
        visit(tree)
        for start, end in sorted(spans, reverse=True):
            lines[start:end] = []
        path.write_text(''.join(lines))
    # Unbound proof slots have an empty fill already; remove their proposed
    # receipt too, proving missing evidence never makes acceptance green.
    (copy/f'mesh/evidence/{task}.json').unlink(missing_ok=True)


def prove_products():
    failures = []
    _, tasks = read(ROOT/'TASKS.tsv')
    for row in tasks:
        copy = local_copy()
        try:
            def run():
                return subprocess.run(row['check'], shell=True, cwd=copy,
                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), capture_output=True, text=True)
            baseline = run()
            empty_fill(copy, row['task'])
            removed = run()
            ok = removed.returncode != 0
            label = 'baseline PASS, empty fill RED' if baseline.returncode == 0 else 'real task RED, empty fill RED'
            print('product '+row['task']+': '+(label if ok else 'FAILED: empty fill accepted'))
            if not ok:
                failures.append(row['task'])
                print(removed.stdout + removed.stderr)
        finally:
            shutil.rmtree(copy)
    return failures


def main():
    parser=argparse.ArgumentParser();parser.add_argument('check',nargs='?',choices=CHECKS);parser.add_argument('--copy',metavar='TASK');args=parser.parse_args()
    if args.copy:
        _,tasks=read(ROOT/'TASKS.tsv')
        if args.copy not in {t['task'] for t in tasks}:parser.error('unknown task')
        mutate(Path.cwd(),'missing');return 0
    selected=(args.check,) if args.check else CHECKS
    failures=[]
    for check in selected:
        copy=local_copy()
        try:
            target='route' if check=='fill-scope' else 'acceptance' if check=='acceptance-scope' else check
            baseline=command(copy,target)
            mutate(copy,check)
            result=command(copy,target)
            expected='validate fill outside writable scope' if check=='fill-scope' else target+': FAIL'
            ok=baseline.returncode==0 and result.returncode!=0 and expected in result.stdout
            print(check+': '+('plant RED (baseline PASS)' if ok else 'plant FAILED'))
            if not ok:failures.append(check);print(baseline.stdout+result.stdout+result.stderr)
        finally:shutil.rmtree(copy)
    if not args.check:
        from route_preflight import prove
        failures.extend(prove())
        failures.extend(prove_products())
    return int(bool(failures))

if __name__=='__main__':raise SystemExit(main())
