"""Derive SCCs and maximum dependency waves directly from the complete wire table."""
import sys
if __name__ == '__main__':
    sys.path.pop(0)
import csv
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
TASK_FIELDS = ['task','deps','brief','inputs','check','hand','piece','citation','estimate_tokens']

def write_table(path,fields,rows):
    with path.open('w') as f:
        w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)

def derive():
    check=runpy.run_path(str(ROOT/'mesh/check.py'))
    errors,slots,wires=check['measure']()
    graph={s['slot']:set() for s in slots}
    for w in wires:
        graph[w['from-slot.output'].split('#')[0]].add(w['to-slot.input'].split('#')[0])
    # Tarjan SCC; sorted traversal gives stable IDs for identical source/model.
    index={};low={};stack=[];active=set();groups=[]
    def visit(v):
        index[v]=low[v]=len(index);stack.append(v);active.add(v)
        for w in sorted(graph[v]):
            if w not in index:visit(w);low[v]=min(low[v],low[w])
            elif w in active:low[v]=min(low[v],index[w])
        if low[v]==index[v]:
            group=[]
            while True:
                w=stack.pop();active.remove(w);group.append(w)
                if w==v:break
            groups.append(sorted(group))
    for v in sorted(graph):
        if v not in index:visit(v)
    groups.sort(key=lambda g:g[0])
    names=['wire-%03d'%i for i in range(len(groups))]
    owner={s:names[i] for i,g in enumerate(groups) for s in g}
    deps={n:set() for n in names}
    for a,bs in graph.items():
        for b in bs:
            if owner[a]!=owner[b]:deps[owner[b]].add(owner[a])
    pending=set(names);completed=set();waves=[]
    while pending:
        ready=sorted(n for n in pending if deps[n]<=completed)
        if not ready:raise ValueError('SCC condensation must be acyclic')
        waves.append(ready);completed.update(ready);pending.difference_update(ready)
    components=[{'task':names[i],'slots':json.dumps(g),'wave':str(next(j+1 for j,w in enumerate(waves) if names[i] in w))} for i,g in enumerate(groups)]
    write_table(ROOT/'mesh/COMPONENTS.tsv',['task','slots','wave'],components)
    tasks=[]; byslot={s['slot']:s for s in slots}
    for i,g in enumerate(groups):
        name=names[i];cost=500+100*len(g)
        brief='Fill and constrain SCC: '+', '.join(g)+'. PRESENT: exact source-proven ports and argument/return/effect wiring. ABSENT: unresolved dispatch, types and unsupported shapes. Failure: re-measure and re-derive; unavailable external signatures or evidence: EXTERNAL. Graph independence does not authorize concurrent writes to shared files.'
        inputs=sorted({byslot[s]['filled-by'].split(':')[0] for s in g if byslot[s]['filled-by']!='EMPTY'})
        tasks.append(dict(zip(TASK_FIELDS,[name,','.join(sorted(deps[name])),brief,','.join(inputs+['mesh/SLOTS.tsv','mesh/WIRES.tsv','mesh/DOMAINS.tsv']),
                         'PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py --component '+name,'no','full program wiring','Runtime and rules',str(cost)])))
    structural=[k for k in check['CHECKS'] if k not in ('package','installed-fresh','whole-repo-clean')]
    for kind in structural:
        tasks.append(dict(zip(TASK_FIELDS,[kind,','.join(sorted(names)),'PRESENT: '+kind+' proof. ABSENT: every measured '+kind+' failure. Failure: re-measure and re-derive; unavailable external evidence: EXTERNAL.','mesh/','PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py --only '+kind,'no',kind,'Runtime and rules','1000'])))
    last=','.join(structural)
    done=[('package',last,'version-consistent distributable','2000','no'),
          ('installed-fresh','package','actual fresh installation with source-bound slip/control observations','6000','yes'),
          ('whole-repo-clean','installed-fresh','whole repository audited and clean outside history','6000','yes')]
    for name,ds,brief,cost,hand in done:
        tasks.append(dict(zip(TASK_FIELDS,[name,ds,'PRESENT: '+brief+'. ABSENT: stale or missing evidence. Failure: re-measure; unavailable owner session or authorized commit facility: EXTERNAL.',
                   'mesh/RECEIPT-'+name+'.json','PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py --only '+name,hand,brief,'DONE',cost])))
    tasks.append(dict(zip(TASK_FIELDS,['zero','whole-repo-clean','PRESENT: all slots, wiring, requirements and done bars proven. ABSENT: every remaining hole. Predicted distance 0. Failure: re-measure and re-derive; external unavailable evidence: EXTERNAL.',
                   'mesh/','PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py','no','distance zero','DONE','1000'])))
    write_table(ROOT/'TASKS.tsv',TASK_FIELDS,tasks)
    lines=['# Makoto seed derived from WIRES','',
           'The measured mesh is incomplete. This is a predicted route to 0, not a consistency claim.',
           'Each explicit wire contributes a dependency. Argument/return feedback is condensed into SCCs; each SCC is one indivisible step. All ready SCCs share a wave, giving maximal graph concurrency. Shared-file writes require serialization and remeasurement.',
           'Failure edges are re-measure and re-derive, or EXTERNAL for unavailable outside evidence. There is no BLOCKED terminal. The route tail is not authorized: no hooks, credentials, commits, pushes or mutating gates are run.',
           'The route TASKS schema is taken from /home/user/mz-route/tools/route/route-USAGE.md. TASKS.tsv contains the complete per-step PRESENT/ABSENT prediction, check and token cost. Runtime steps cite the exact README heading Runtime and rules; done bars cite WORDS.tsv DONE.',
           '']
    for j,wave in enumerate(waves,1):lines.append('Wave '+str(j)+': '+', '.join(wave))
    lines += ['','After graph waves: all structural proof checks → package → installed-fresh → whole-repo-clean → zero.',
              'At zero: exact types, complete calls/effects, reachable slots, requirements neither missing nor over-constrained, and all done bars pass against the same inputs.',
              'External evidence remains absent. Clean git status cannot be met while these changes are deliberately uncommitted. Full-program dynamic-dispatch and exact-type proof remain substantial implementation work.','']
    (ROOT/'PLAN.md').write_text('\n'.join(lines))
    mesh=[]
    for name in names:
        mesh.append({'hole':name,'check':'PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py --component '+name,'plant':'PYTHONDONTWRITEBYTECODE=1 python3 mesh/plants.py '+name,'piece':'full program wiring','citation':'Runtime and rules','status':'ABSENT'})
    for kind in check['CHECKS']:
        mesh.append({'hole':kind,'check':'PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py --only '+kind,
                     'plant':'PYTHONDONTWRITEBYTECODE=1 python3 mesh/plants.py '+kind,
                     'piece':kind,'citation':'DONE' if kind in ('package','installed-fresh','whole-repo-clean') else 'Runtime and rules',
                     'status':'PRESENT' if not errors[kind] else 'ABSENT'})
    mesh.append({'hole':'zero','check':'PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py','plant':'PYTHONDONTWRITEBYTECODE=1 python3 mesh/plants.py inventory','piece':'distance zero','citation':'DONE','status':'ABSENT'})
    write_table(ROOT/'MESH.tsv',['hole','check','plant','piece','citation','status'],mesh)
    verdict={'slots':len(slots),'wires':len(wires),'empty':sum(s['filled-by']=='EMPTY' for s in slots),
             'missing':len(errors['missing']),'over':len(errors['over']),'check.py exit':int(any(errors.values())),
             'waves':len(waves)+5,'steps':len(tasks),'unresolved ports':len(errors['types']),'wire mismatches':len(errors['wires']),
             'unreachable slots':len(errors['reachable'])}
    (ROOT/'VERDICT-MESH.txt').write_text('REPO=makoto\n'+'\n'.join(str(k)+'='+str(v) for k,v in verdict.items())+'\nINCOMPLETE: no zero proof; see mesh/README.md for proof boundaries.\n')
    (ROOT/'VERDICT-SEED.txt').write_text('REPO=makoto\nDERIVED from WIRES SCC condensation\n'+str(len(waves)+5)+' waves; '+str(len(tasks))+' steps\nPredicted end=0; measured mesh exit=1\nFailure=re-measure or EXTERNAL\n')
    return verdict

if __name__=='__main__':
    print(json.dumps(derive(),sort_keys=True))
