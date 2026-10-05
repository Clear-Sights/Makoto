"""Measure every head entry and remove each owner predicate and family in copies.

The family plant removes the predicate closure of the register's section. Shared
predicates are removed once, including owners placed by the needs line in another
module. Every affected entry must independently turn red; judgment is never green.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def run(root, selectors, report):
    return subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                           '--junitxml='+str(report), *selectors], cwd=root,
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                          capture_output=True, text=True)


def results(report):
    return {case.get('name'): not any(case.find(tag) is not None for tag in ('failure','error','skipped'))
            for case in ET.parse(report).iter('testcase')}


def plant(cases, predicates, label):
    with tempfile.TemporaryDirectory(prefix='makoto-goal-') as folder:
        copy = Path(folder)
        for name in ('plugin','tests'):
            shutil.copytree(ROOT/name,copy/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copyfile(ROOT/'REGISTER.md',copy/'REGISTER.md')
        for predicate in sorted(predicates):
            module,function = predicate.split('.')
            with (copy/'plugin/makoto2'/(module+'.py')).open('a') as stream:
                stream.write('\n'+function+' = lambda *args, **kwargs: []\n')
        report = copy/'result.xml'
        outcome = run(copy,['tests/test_goal.py::test_fake['+c['id']+']' for c in cases],report)
        measured = results(report) if report.exists() else {}
        reds = {c['id']: measured.get('test_fake['+c['id']+']') is False for c in cases}
        # Import errors or missing collected cases cannot prove predicate necessity.
        passed = outcome.returncode == 1 and all(reds.values())
        print(label+': '+('RED '+str(len(reds))+'/'+str(len(reds)) if passed else 'FAILED'),flush=True)
        return dict(plant=label,predicates=sorted(predicates),entries=reds,
                    red=passed,exit_code=outcome.returncode)


def main():
    cases=json.loads((ROOT/'tests/fixtures/goal.json').read_text())
    evaluable=[c for c in cases if c['state']=='EVALUABLE']
    routine=json.loads((ROOT/'tests/fixtures/honest_writes.json').read_text())
    with tempfile.TemporaryDirectory(prefix='makoto-baseline-') as folder:
        report=Path(folder)/'result.xml'
        baseline=run(ROOT,['tests/test_goal.py'],report)
        measured=results(report) if report.exists() else {}
    caught={c['id']: measured.get('test_fake['+c['id']+']') is True for c in evaluable}
    honest={c['id']: measured.get('test_honest['+c['id']+']') is True for c in evaluable}
    honest.update({'routine:'+c['id']: measured.get('test_routine_honest['+c['id']+']') is True
                   for c in routine})
    plants=[]
    for predicate in sorted({c['predicate'] for c in evaluable}):
        selected=[c for c in evaluable if c['predicate']==predicate]
        plants.append(plant(selected,{predicate},predicate))
    for family in dict.fromkeys(c['family'] for c in cases):
        selected=[c for c in evaluable if c['family']==family]
        plants.append(plant(selected,{c['predicate'] for c in selected},'family '+family))
    families={f:dict(caught=sum(caught.get(c['id'],False) for c in cases if c['family']==f),
                     total=sum(c['family']==f for c in cases),
                     not_evaluable=[c['id'] for c in cases if c['family']==f and c['state']=='NOT-EVALUABLE'])
              for f in dict.fromkeys(c['family'] for c in cases)}
    paths=list((ROOT/'plugin').rglob('*'))+[ROOT/name for name in
        ('REGISTER.md','WORDS.tsv','tests/test_goal.py','tests/fixtures/goal.json',
         'tests/fixtures/honest_writes.json','mesh/goal.py')]
    pins={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(paths) if p.is_file() and '__pycache__' not in p.parts}
    passed=baseline.returncode==0 and all(p['red'] for p in plants)
    report=dict(result='pass' if passed else 'fail',source_pins=pins,
        baseline_exit_code=baseline.returncode,stdout=baseline.stdout,stderr=baseline.stderr,
        catches=sum(caught.values()),head_entries=len(cases),families=families,
        not_evaluable=[dict(id=c['id'],reason=c['reason']) for c in cases if c['state']=='NOT-EVALUABLE'],
        false_fires=sum(not x for x in honest.values()),honest_cases=len(honest),plants=plants,
        routine_honest={c['id']:honest['routine:'+c['id']] for c in routine},
        scope='Fixed native hook sequences; structured gate facts are settled tool results. Family plants remove the register section predicate closure; shared owners follow needs. No judgment inference.',
        reproduction='PYTHONDONTWRITEBYTECODE=1 python3 mesh/goal.py')
    (ROOT/'mesh/evidence/goal.json').write_text(json.dumps(report,indent=2)+'\n')
    print('catches '+str(report['catches'])+'/'+str(len(cases))+'; false fires '+str(report['false_fires'])+'/'+str(len(honest)))
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
