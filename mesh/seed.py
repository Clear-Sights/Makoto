"""Derive route tasks and concurrency waves from final-program openings only."""
from pathlib import Path
import argparse
import ast
import csv

ROOT = Path(__file__).resolve().parents[1]
INPUT = 'PROGRAM_INPUT'
OUTPUT = 'PROGRAM_OUTPUT'
TASK_FIELDS = ('task','deps','brief','inputs','check','hand','piece','citation','estimate_tokens')
EXTERNAL_SLOTS = set()


def read(path):
    with path.open(newline='') as f:return list(csv.DictReader(f,delimiter='\t'))


def write(path,rows,fields):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)


def callers(paths):
    """Include live callers and tests; historical references are read-only."""
    modules = {Path(path).stem for path in paths}
    found = set(paths)
    for path in sorted(ROOT.rglob('*.py')):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(('mesh/', '.')) or rel == 'tests/acceptance_tasks.py':
            continue
        text = path.read_text()
        try:
            nodes = ast.walk(ast.parse(text))
            imported = set()
            for node in nodes:
                if isinstance(node, ast.Import):
                    imported.update(a.name.split('.')[-1] for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.add((node.module or '').split('.')[-1])
                    imported.update(a.name for a in node.names)
        except SyntaxError:
            imported = set()
        if modules & imported or any(source in text for source in paths):
            found.add(rel)
    return sorted(found)


def task_class(task):
    return task.split('-', 1)[0]


def measured_costs(path):
    with path.open(newline='') as f:
        reader = csv.DictReader(f, delimiter='\t')
        if reader.fieldnames != ['repo', 'task', 'class', 'tokens', 'passed', 'source']:
            raise ValueError('invalid COSTS columns')
        rows = list(reader)
    if not rows:
        raise ValueError('COSTS requires a measured attempt')
    costs = {}
    passing = []
    for row in rows:
        if (None in row or any(v is None for v in row.values())
                or not row['repo'].strip() or not row['task'] or not row['source'].strip()
                or row['class'] != task_class(row['task'])
                or row['passed'] not in ('yes', 'no')
                or not row['tokens'].isdigit() or int(row['tokens']) <= 0):
            raise ValueError('invalid measured COSTS row')
        tokens = int(row['tokens'])
        if row['passed'] == 'yes':
            passing.append(tokens)
            kind = row['class']
            costs[kind] = min(costs.get(kind, tokens), tokens)
    if not passing:
        raise ValueError('COSTS requires a passing measured run')
    return costs, max(passing)


def derive(plan_only=False):
    _, floor = measured_costs(ROOT/'mesh/COSTS.tsv')
    measured = [row for row in read(ROOT/'mesh/COSTS.tsv') if row['passed'] == 'yes']
    slots={s['slot']:s for s in read(ROOT/'mesh/SLOTS.tsv')}
    requirements={r['requirement']:r for r in read(ROOT/'mesh/REQUIREMENTS.tsv')}
    deps={s:{'subtract'} for s in slots if s not in (INPUT,OUTPUT)}
    for w in read(ROOT/'mesh/WIRES.tsv'):
        a=w['source'].split('#')[0];b=w['target'].split('#')[0]
        if a!=INPUT and b!=OUTPUT:deps[b].add(a)
    deps['subtract']=set();deps['zero']=set(slots)-{INPUT,OUTPUT}
    tasks=[];mesh=[];predictions=[]
    for id,parents in deps.items():
        slot=slots.get(id)
        exact = [int(row['tokens']) for row in measured if row['repo'] == ROOT.name and row['task'] == id]
        own = [int(row['tokens']) for row in measured if row['repo'] == ROOT.name and row['class'] == task_class(id)]
        same = [int(row['tokens']) for row in measured if row['class'] == task_class(id)]
        cost = min(exact) if exact else max(own or same or [floor])
        refs=slot['requirements'].split(',') if slot else ['done']
        citation=requirements[refs[0]]['source'].removeprefix('WORDS.tsv:')
        # Route resolves owner words from WORDS_FILES; SPIRIT headings are literal Markdown headings.
        if citation.startswith('docs-def:README.md#'):citation=citation.split('#')[1]
        if citation.startswith('SPIRIT.md#'):citation=citation.split('#')[1]
        model_command='PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py --task '+id
        command='PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/acceptance_tasks.py::test_'+id
        if id=='subtract':
            removals=read(ROOT/'mesh/SUBTRACT.tsv')
            inputs=','.join(sorted({r['path'] for r in removals})+['mesh/SUBTRACT.tsv','mesh/SUBTRACT-KEPT.tsv'])
            present='preserved reference originals and retained live infrastructure recorded in mesh/SUBTRACT-KEPT.tsv; scope only the exact SUBTRACT units; exclude pinned mesh/check.py and mesh/plants.py, all reference files and retained mesh/seed.py; if originals are already absent, verify and finish in this first attempt without edits'
            absent='AST-identical reference originals at active units: '+', '.join(r['path']+':'+r['unit'] for r in removals)
        elif id=='zero':
            inputs='mesh/evidence/zero.json'
            present='model contracts equal requirement envelopes; implementation done only when every executable product acceptance passes; run PYTHONDONTWRITEBYTECODE=1 python3 mesh/zero.py to write the required output mesh/evidence/zero.json; measurement inputs are read-only'
            absent='model missing/over constraints; stale or missing evidence cannot imply implementation done'
        else:
            candidate=slot['filled-by'] or 'OPEN'
            paths=sorted({x.split(':')[0] for x in candidate.split(';') if x!='OPEN'} |
                         {f['path'] for f in read(ROOT/'mesh/FILLS.tsv') if f['slot']==id})
            inputs=','.join(callers(paths)+['mesh/SLOTS.tsv', 'mesh/FILLS.tsv', 'tests/acceptance_tasks.py', f'mesh/evidence/{id}.json'] + (['plugin/makoto2/lifecycle.py'] if id in {'validate','package','fresh','audit','join','handoff'} else []))
            present='realized '+id+' ports satisfying '+','.join(refs)+'; candidate '+candidate+'; implement product code and run acceptance; evidence files are optional check outputs, never proof inputs'
            absent='unrealized behavior and stale/missing current evidence'
        brief=f'Local pytest, mesh/check.py, mesh/plants.py and the task check are authorized. PRESENT: {present}. ABSENT: {absent}. Cost: {cost} tokens. Failure: re-measure changed input and re-derive waves; unavailable operator or outside evidence = EXTERNAL.'
        if id=='register':
            # Owner decides register amendments: realize the ports against the approved register; never amend it.
            brief+=' Load, enforce and replay the CURRENT shipped register exactly. Never amend it. Proposed amendments remain in mesh/evidence/register-proposal.md for Gabriel; approval is not a route obligation or dependency.'
            inputs+=',plugin/makoto2/rows.tsv,tests/sources.tsv'
        if id not in {'zero', 'subtract'}:
            from acceptance import references
            tests = references(ROOT, 'tests/acceptance_tasks.py::test_'+id)
            inputs = ','.join(inputs.split(',') + sorted(tests - set(inputs.split(','))))
        tasks.append(dict(task=id,deps=','.join(sorted(parents)),brief=brief,inputs=inputs,check=command,hand='no',piece=id,citation=citation,estimate_tokens=cost))
        mesh.append(dict(hole=id,check=model_command,plant='PYTHONDONTWRITEBYTECODE=1 python3 mesh/plants.py --copy '+id,piece=id,citation=citation,status='SHAPE_PRESENT',realization=slot['fill-status'] if slot else 'MODEL_ONLY'))
        predictions.append(dict(task=id,shape='PRESENT',implementation='REMOVED' if id=='subtract' else slot['fill-status'] if slot else 'UNPROVEN',evidence='EXTERNAL' if id in EXTERNAL_SLOTS else 'UNMEASURED',cost_tokens=cost))
    waves=[];pending=set(deps);done=set()
    while pending:
        ready=sorted(t for t in pending if deps[t]<=done)
        if not ready:raise ValueError('wiring cycle: re-measure the chosen layer')
        waves.append(ready);done.update(ready);pending.difference_update(ready)
    if not plan_only:
        write(ROOT/'TASKS.tsv',tasks,TASK_FIELDS)
        write(ROOT/'MESH.tsv',mesh,('hole','check','plant','piece','citation','status','realization'))
    write(ROOT/'mesh/PREDICTIONS.tsv',predictions,tuple(predictions[0]))
    existing_plan = (ROOT/'PLAN.md').read_text()
    config = existing_plan.split('```text\n', 1)[1].split('```', 1)[0]
    config = '\n'.join('REPO_DIR='+str(ROOT) if line.startswith('REPO_DIR=') else line for line in config.splitlines())
    lines=['# Makoto: top-down seed from final-program wiring','',
      'Requirements open ports; transformed wires order work. Raw program inputs are local slot bindings (SLOTS input-sources). WIRE-RULE.tsv records the applied classification; wire_rule.py rejects identity wires and detects missing transformed passes. Layer 1 closes only source-backed definite constraints. Layers 2+ use signed deterministic feedback within that closed space: surplus deletion reduces excess, while required deletion increases missing and is forbidden. SymPy simplifies every slot relation before and after the loop. tighten.py computes the least finite requirement relations to a fixpoint, and check.py rejects a stale TIGHTEN.tsv. SUBTRACT is first. Each later wave contains every ready slot, giving maximal concurrency under this one-layer dependency graph. Candidate units in shared files must be edited by one writer or re-measured into disjoint scopes; evidence files are per slot.', '',
      'The shape model passes independently of implementation. OPEN, PARTIAL and CANDIDATE are explicit implementation absences, not proof receipts. TASKS execute product acceptance, including blocking and silent cases. MESH checks the separate declarative contract. Open evidence obligations fail product acceptance. PREDICTIONS.tsv records this distinction. Each task brief predicts PRESENT/ABSENT and a token cost from mesh/COSTS.tsv. Estimates follow route-audit: use the cheapest passing exact task in this checkout, otherwise the largest passing checkout/class or cross-repository class measurement; unmeasured classes use the largest passing run overall. A class is the task-name prefix before the first hyphen (including subtract and fill). Failed attempts never set estimates. The project rule stops a job over twice its cheapest logged passing run of the same class.', '',
      'Failure edges are re-measure and re-derive, or EXTERNAL for unavailable owner decisions, current CI receipts, installation or audit evidence. EXTERNAL returns to the same slot on changed input. There is no BLOCKED terminal and no countdown decrement for stale or absent evidence. The join emits done only when every current proof input is present.', '',
      'Route TASKS format: /home/user/mz-route/tools/route/route-USAGE.md and route-digest.md. All MESH rows correspond to task ids and have plants that mutate the current disposable working tree. Local checks and fixed-input hook replay are authorized by FIX16. Register amendments require Gabriel; merging remains with Gabriel.', '',
      'Route configuration:',
      '```text','REPO_DIR=/home/user/makoto','WHY=Makoto prevents blindspots through detection','WORDS_FILES=WORDS.tsv,SPIRIT.md,mesh/reference/docs-def-README.md','MESH_FILE=MESH.tsv','SEED_FILE=PLAN.md','GATE_CMD=PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py','PLANTS_CMD=PYTHONDONTWRITEBYTECODE=1 python3 mesh/plants.py','```','',
      'MESH checks declare model contracts; TASKS checks execute product acceptance. Missing external evidence keeps the corresponding task open.', '']
    for n,wave in enumerate(waves,1):
        cost=sum(int(t['estimate_tokens']) for t in tasks if t['task'] in wave)
        lines.append(f'Wave {n}: '+', '.join(wave)+f' (predicted {cost} tokens)')
    lines+=['','At the final zero step: model distance = missing + over + structural violations = 0. Implementation distance reaches 0 only after current register, validation, package, fresh-session and whole-repo evidence realize the join contract. No such external receipts are invented in this pass.','',
      'Required route outputs: each slot owns its declared mesh/evidence/<slot>.json receipt; Register amendments remain optional proposals in mesh/evidence/register-proposal.md, outside the task DAG. Receipts are outputs only; acceptance executes the product. The zero task writes mesh/evidence/zero.json by running PYTHONDONTWRITEBYTECODE=1 python3 mesh/zero.py. These files are retained proof artifacts for measurement and handoff, including reports of missing or external evidence. Zero pins mesh/, PLAN.md, TASKS.tsv and MESH.tsv and executes product acceptance without using receipts as proof; its output excludes itself from source pins. Model zero and implementation completion remain separate.', '',
      'Route cleanup leftovers removed: mesh/reference/seed.py (unused historical generator; preserved in git history). Required reference/docs-def-README.md and reference/types.py remain pinned source and subtraction evidence.', '',
      'Scope: final Makoto detection, portable handoff, proof interfaces and seed. Foreign DetIO/Tiller/Countdown clauses are exclusions. The historical README and subtraction types are required references; unused reference seed was removed; local pytest, mesh checks, plants and fixed-input replay are authorized; no credentials, publishing or merges.']
    start = lines.index('```text')
    end = lines.index('```', start + 1)
    lines[start+1:end] = config.rstrip().splitlines()
    (ROOT/'PLAN.md').write_text('\n'.join(lines)+'\n')
    return waves,tasks

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan-only',action='store_true',help='derive PLAN and mesh predictions without writing root route tables')
    derive(parser.parse_args().plan_only)
