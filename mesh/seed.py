"""Derive route tasks and concurrency waves from final-program openings only."""
from pathlib import Path
import argparse
import csv

ROOT = Path(__file__).resolve().parents[1]
INPUT = 'PROGRAM_INPUT'
OUTPUT = 'PROGRAM_OUTPUT'
TASK_FIELDS = ('task','deps','brief','inputs','check','hand','piece','citation','estimate_tokens')
EXTERNAL_SLOTS = {'register','fresh','audit'}


def read(path):
    with path.open(newline='') as f:return list(csv.DictReader(f,delimiter='\t'))


def write(path,rows,fields):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)


def measured_costs(path):
    with path.open(newline='') as f:
        reader = csv.DictReader(f, delimiter='\t')
        if reader.fieldnames != ['task', 'tokens', 'source']:
            raise ValueError('invalid COSTS columns')
        rows = list(reader)
    if not rows:
        raise ValueError('COSTS requires a measured attempt')
    costs = {}
    for row in rows:
        if (None in row or any(v is None for v in row.values())
                or not row['task'] or not row['source'].strip()
                or not row['tokens'].isdigit() or int(row['tokens']) <= 0):
            raise ValueError('invalid measured COSTS row')
        tokens = int(row['tokens'])
        costs[row['task']] = min(costs.get(row['task'], tokens), tokens)
    return costs, min(costs.values())


def derive(plan_only=False):
    costs, floor = measured_costs(ROOT/'mesh/COSTS.tsv')
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
        cost=costs.get(id, floor)
        refs=slot['requirements'].split(',') if slot else ['done']
        citation=requirements[refs[0]]['source'].removeprefix('WORDS.tsv:')
        # Route resolves owner words from WORDS_FILES; SPIRIT headings are literal Markdown headings.
        if citation.startswith('docs-def:README.md#'):citation=citation.split('#')[1]
        if citation.startswith('SPIRIT.md#'):citation=citation.split('#')[1]
        command='PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py --task '+id
        if id=='subtract':
            inputs='mesh/reference/,mesh/SUBTRACT.tsv'
            present='only requirement-needed units in seed; old generators preserved as reference'
            absent='bottom-up inventory and SCC generators at active paths'
        elif id=='zero':
            inputs='mesh/,PLAN.md,TASKS.tsv,MESH.tsv'
            present='model contracts equal requirement envelopes; implementation done only with all current evidence'
            absent='model missing/over constraints; stale or missing evidence cannot imply implementation done'
        else:
            candidate=slot['filled-by'] or 'OPEN'
            paths=sorted({x.split(':')[0] for x in candidate.split(';') if x!='OPEN'})
            inputs=','.join(paths+[f'mesh/evidence/{id}.json'])
            present='realized '+id+' ports satisfying '+','.join(refs)+'; candidate '+candidate
            absent='unrealized behavior and stale/missing current evidence'
        brief=f'PRESENT: {present}. ABSENT: {absent}. Cost: {cost} tokens. Failure: re-measure changed input and re-derive waves; unavailable operator or outside evidence = EXTERNAL.'
        tasks.append(dict(task=id,deps=','.join(sorted(parents)),brief=brief,inputs=inputs,check=command,hand='yes' if id=='register' else 'no',piece=id,citation=citation,estimate_tokens=cost))
        mesh.append(dict(hole=id,check=command,plant='PYTHONDONTWRITEBYTECODE=1 python3 mesh/plants.py --copy '+id,piece=id,citation=citation,status='SHAPE_PRESENT',realization=slot['fill-status'] if slot else 'MODEL_ONLY'))
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
    lines=['# Makoto: top-down seed from final-program wiring','',
      'Requirements open ports; transformed wires order work. Raw program inputs are local slot bindings (SLOTS input-sources). WIRE-RULE.tsv records the applied classification; wire_rule.py rejects identity wires and detects missing transformed passes. Layer 1 closes only source-backed definite constraints. Layers 2+ use signed deterministic feedback within that closed space: surplus deletion reduces excess, while required deletion increases missing and is forbidden. SymPy simplifies every slot relation before and after the loop. tighten.py computes the least finite requirement relations to a fixpoint, and check.py rejects a stale TIGHTEN.tsv. SUBTRACT is first. Each later wave contains every ready slot, giving maximal concurrency under this one-layer dependency graph. Candidate units in shared files must be edited by one writer or re-measured into disjoint scopes; evidence files are per slot.', '',
      'The shape model passes independently of implementation. OPEN, PARTIAL and CANDIDATE are explicit implementation absences, not proof receipts. TASKS check the declared model obligations; they do not run hooks, gates or certify implementation completion. PREDICTIONS.tsv records this distinction. Each task brief predicts PRESENT/ABSENT and a token cost from mesh/COSTS.tsv. Measured tasks use their cheapest logged attempt; unmeasured tasks use the cheapest logged attempt overall as their floor. The project rule stops a job over twice its cheapest logged run.', '',
      'Failure edges are re-measure and re-derive, or EXTERNAL for unavailable owner decisions, current CI receipts, installation or audit evidence. EXTERNAL returns to the same slot on changed input. There is no BLOCKED terminal and no countdown decrement for stale or absent evidence. The join emits done only when every current proof input is present.', '',
      'Route TASKS format: /home/user/mz-route/tools/route/route-USAGE.md and route-digest.md. All MESH rows correspond to task ids and have plants that mutate the current disposable working tree. This is a reviewable plan; route execution and its tail are outside this request. Register amendments require Gabriel; merging remains with Gabriel.', '',
      'Configuration for a later authorized model-only route:',
      '```text','REPO_DIR=/home/user/makoto','WHY=Makoto prevents blindspots through detection','WORDS_FILES=WORDS.tsv,SPIRIT.md,mesh/reference/docs-def-README.md','MESH_FILE=MESH.tsv','SEED_FILE=PLAN.md','GATE_CMD=PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py','PLANTS_CMD=PYTHONDONTWRITEBYTECODE=1 python3 mesh/plants.py','```','',
      'These are declarations, not commands executed during formation. Model checks do not replace the product acceptance gates.', '']
    for n,wave in enumerate(waves,1):
        cost=sum(int(t['estimate_tokens']) for t in tasks if t['task'] in wave)
        lines.append(f'Wave {n}: '+', '.join(wave)+f' (predicted {cost} tokens)')
    lines+=['','At the final zero step: model distance = missing + over + structural violations = 0. Implementation distance reaches 0 only after current register, validation, package, fresh-session and whole-repo evidence realize the join contract. No such external receipts are invented in this pass.','',
      'Scope: final Makoto detection, portable handoff, proof interfaces and seed. Foreign DetIO/Tiller/Countdown clauses are exclusions. Historical docs and old mesh artifacts are reference; no hook invocation/configuration, credentials, gate runs, publishing or merges.']
    start = lines.index('```text')
    end = lines.index('```', start + 1)
    lines[start+1:end] = config.rstrip().splitlines()
    (ROOT/'PLAN.md').write_text('\n'.join(lines)+'\n')
    return waves,tasks

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan-only',action='store_true',help='derive PLAN and mesh predictions without writing root route tables')
    derive(parser.parse_args().plan_only)
