"""Deterministic final-program shape checker. Never imports or executes runtime code.
Zero certifies this declarative model, not its candidate implementation or receipts.
"""
from pathlib import Path
import argparse
import ast
import csv
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
MESH = ROOT / 'mesh'
CHECKS = ('schema', 'wires', 'reachable', 'trace', 'coverage', 'fills', 'missing', 'over', 'subtractions', 'route', 'wire-rule', 'tighten', 'costs')
INPUT = 'PROGRAM_INPUT'
OUTPUT = 'PROGRAM_OUTPUT'
SOURCE_PATHS = {'WORDS.tsv','SPIRIT.md','mesh/reference/docs-def-README.md'}
ATOMS = {'Bytes', 'String', 'JSON', 'Record', 'Finding', 'Evidence', 'Artifact', 'Verdict'}
CONSTRUCTORS = {'one': 1, 'many': 1, 'option': 1, 'set': 1, 'list': 1, 'map': 2}
TABLES = {'SLOTS': ('slot','inputs','outputs','requirements','loosest','filled-by','fill-status','input-sources','output-from'),
          'WIRES': ('wire','source','target','requirements'),
          'REQUIREMENTS': ('requirement','source','text','scope','slot','port','universe','allowed','required','math-type'),
          'CONSTRAINTS': ('constraint','requirement','slot','port','accepts','derivation'),
          'FILLS': ('path','unit','slot','reason'), 'SUBTRACT': ('path','unit','reason'),
          'TRACE': ('requirement','source','verdict','tests'), 'SOURCES': ('path','sha256')}
TASK_FIELDS = ('task','deps','brief','inputs','check','hand','piece','citation','estimate_tokens')
# Nominal payloads are open records: these fields are required, extra fields permitted.
# No implementation class, exact collection length, rule order or serialization is imposed.
PAYLOADS = {
 'Record': 'obs:list[settled effect{seq,tool,input,output,exit:option[int],failed,objects:set[String],written:set[String],created:set[String],send:String,search:option[scope,query,empty]}]; turn_start; user_texts:list[String]',
 'Finding': '{row:String,message:String,objects:list[String]}',
 'Evidence': '{selected_input_digest:String,observations:list[map[String,JSON]],source_pins:map[String,String],result:pass|fail|absent}',
 'Artifact': '{contents:map[String,Bytes],input_digest:String}',
 'Verdict': '{present:set[String],absent:set[String],external:set[String],input_digest:String}',
}


def read(path):
    with path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        rows = list(reader)
        return tuple(reader.fieldnames or ()), rows


def type_tree(value):
    tokens = re.findall(r'[A-Za-z]+|[\[\],]', value)
    if ''.join(tokens) != value:
        raise ValueError('invalid type '+value)
    pos = 0
    def parse():
        nonlocal pos
        name = tokens[pos]; pos += 1
        if name in ATOMS:
            return (name,)
        if name not in CONSTRUCTORS or tokens[pos] != '[':
            raise ValueError('unknown shape '+name)
        pos += 1; args = [parse()]
        while tokens[pos] == ',':
            pos += 1; args.append(parse())
        if tokens[pos] != ']' or len(args) != CONSTRUCTORS[name]:
            raise ValueError('shape arity '+name)
        pos += 1
        return (name, *args)
    result = parse()
    if pos != len(tokens):
        raise ValueError('trailing shape')
    # many has a collection carrier, one a scalar/optional/open record.
    if result[0] not in ('one','many') or (result[0]=='many' and result[1][0] not in ('set','list','map')):
        raise ValueError('missing multiplicity/collection')
    return result


def units(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    found = {'<module>'}
    def walk(node, prefix=''):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                name = prefix+child.name; found.add(name); walk(child,name+'.')
            else:
                walk(child,prefix)
    walk(tree)
    return found


def old_unit_present(current,reference,name):
    def fingerprint(path):
        tree=ast.parse(path.read_text())
        if name=='<module>':return ast.dump(tree,include_attributes=False)
        selected=[]
        def walk(node,prefix=''):
            for child in ast.iter_child_nodes(node):
                if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                    n=prefix+child.name
                    if n==name:selected.append(ast.dump(child,include_attributes=False))
                    walk(child,n+'.')
                else:walk(child,prefix)
        walk(tree)
        return selected
    return fingerprint(current)==fingerprint(reference)


def errors(root=ROOT):
    mesh = root/'mesh'; bad = {c:[] for c in CHECKS}
    tables = {}
    for name, fields in TABLES.items():
        try:
            header, rows = read(mesh/(name+'.tsv'))
            if header != fields or any(None in r or any(v is None for v in r.values()) for r in rows):
                bad['schema'].append('invalid columns '+name)
            tables[name] = rows
        except (OSError,ValueError) as e:
            bad['schema'].append(str(e)); tables[name] = []
    S=tables['SLOTS']; R=tables['REQUIREMENTS']; W=tables['WIRES']; C=tables['CONSTRAINTS']
    slots={s['slot']:s for s in S}; reqs={r['requirement']:r for r in R}
    for name,key in [('SLOTS','slot'),('WIRES','wire'),('REQUIREMENTS','requirement'),('CONSTRAINTS','constraint')]:
        values=[r[key] for r in tables[name]]
        if len(values)!=len(set(values)) or not values:bad['schema'].append('empty or duplicate '+name)
    ports={}; domains={}
    for s in S:
        for side in ('inputs','outputs'):
            try:
                value=json.loads(s[side])
                if not isinstance(value,dict):raise ValueError('port map')
                for p,t in value.items():ports[(s['slot'],side,p)]=type_tree(t)
            except (ValueError,TypeError,IndexError,KeyError) as e:bad['schema'].append(s['slot']+' '+str(e))
        if s['fill-status'] not in ('OPEN','CANDIDATE','PARTIAL'):bad['schema'].append('fill status '+s['slot'])
    if INPUT not in slots or OUTPUT not in slots:bad['schema'].append('boundaries absent')
    if slots.get(INPUT,{}).get('inputs')!='{}' or slots.get(OUTPUT,{}).get('outputs')!='{}':bad['schema'].append('boundary direction')
    for r in R:
        try:
            universe,allowed,required=[set(json.loads(r[k])) for k in ('universe','allowed','required')]
            if not required or not required<=allowed<=universe:raise ValueError('invalid requirement relation')
            domains[r['requirement']]=(universe,allowed,required)
            type_tree(r['math-type'])
        except (ValueError,TypeError,IndexError,KeyError) as e:bad['schema'].append(r['requirement']+' '+str(e))
    # Authority pins reject stale derivations. Coverage of WORDS is independent of slot declarations.
    if {p['path'] for p in tables['SOURCES']} != SOURCE_PATHS or len(tables['SOURCES'])!=len(SOURCE_PATHS):bad['schema'].append('missing authority pins')
    for pin in tables['SOURCES']:
        p=root/pin['path']
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=pin['sha256']:bad['schema'].append('source changed '+pin['path'])
    _,words=read(root/'WORDS.tsv')
    for word in words:
        if not any(r['source']=='WORDS.tsv:'+word['id'] for r in R):bad['coverage'].append('uncaptured WORDS '+word['id'])
    for r in R:
        source=r['source']
        if source.startswith('WORDS.tsv:'):
            exists=source.split(':',1)[1] in {x['id'] for x in words}
        else:
            prefix,sep,heading=source.partition('#')
            p=root/('mesh/reference/docs-def-README.md' if prefix=='docs-def:README.md' else prefix)
            exists=bool(sep and p.is_file() and re.search(r'^#+ '+re.escape(heading)+r'\s*$',p.read_text(),re.M))
        if not exists:bad['schema'].append('unresolved citation '+source)
    traces = {t['requirement']: t for t in tables['TRACE']}
    if len(traces) != len(tables['TRACE']) or set(traces) != set(reqs):
        bad['trace'].append('TRACE coverage or duplicate')
    for r in R:
        t = traces.get(r['requirement'], {})
        if t.get('verdict') != 'TRACED' or t.get('source') != r['source']:
            bad['trace'].append('requirement without TRACED source: ' + r['requirement'])
        expected_test = 'tests/acceptance_tasks.py::test_' + r['slot']
        if t.get('tests') != expected_test or not (root/'tests/acceptance_tasks.py').is_file() or 'test_'+r['slot'] not in units(root/'tests/acceptance_tasks.py'):
            bad['trace'].append('missing product acceptance: '+r['requirement'])
    forward={s:set() for s in slots}; backward={s:set() for s in slots}; connected=set()
    for w in W:
        try:
            a,p=w['source'].split('#'); b,q=w['target'].split('#')
            left=ports[(a,'outputs',p)]; right=ports[(b,'inputs',q)]
            if left!=right:bad['wires'].append(w['wire']+' type mismatch')
            forward[a].add(b); backward[b].add(a);connected.update(((a,'outputs',p),(b,'inputs',q)))
            refs=set(filter(None,w['requirements'].split(',')))
            if not refs or not refs<=reqs.keys():bad['trace'].append(w['wire']+' no requirement')
            relevant=set(slots[b if b!=OUTPUT else a]['requirements'].split(','))
            if not refs<=relevant:bad['trace'].append(w['wire']+' foreign requirement')
        except (ValueError,KeyError):bad['wires'].append(w['wire']+' invalid endpoint')
    # Folded raw inputs remain local bindings, rather than flexibility wires.
    for slot in S:
        for q, source in json.loads(slot['input-sources']).items():
            a, p = source.split('#'); b = slot['slot']
            if a == INPUT:
                if ports.get((a,'outputs',p)) != ports.get((b,'inputs',q)):
                    bad['wires'].append('local binding type mismatch '+source)
                connected.update(((a,'outputs',p),(b,'inputs',q)))
                forward[a].add(b); backward[b].add(a)
    try:
        from wire_rule import classify
        decisions = classify(mesh)
        bad['wire-rule'].extend(r['wire or pair']+' '+r['verdict'] for r in decisions if r['verdict'] != 'KEEP')
        # WIRE-RULE records the applied revision, including its folded wires.
    except (OSError, ValueError, KeyError, TypeError) as e:
        bad['wire-rule'].append(str(e))
    for endpoint in ports:
        if endpoint not in connected:bad['wires'].append('unwired '+str(endpoint))
    def reach(start,graph):
        seen=set(); todo=[start]
        while todo:
            n=todo.pop()
            if n not in seen:seen.add(n);todo.extend(graph.get(n,()))
        return seen
    path=reach(INPUT,forward)&reach(OUTPUT,backward)
    for s in S:
        id=s['slot'];refs=set(filter(None,s['requirements'].split(',')))
        if id not in path:bad['reachable'].append(id+' off input/output path')
        if not refs or not refs<=reqs.keys():bad['trace'].append(id+' no valid requirement')
        if id not in (INPUT,OUTPUT) and not any(r['slot']==id for r in R):bad['trace'].append(id+' no direct requirement')
    for r in R:
        endpoint=(r['slot'],'outputs',r['port'])
        if endpoint not in ports or endpoint not in connected or r['requirement'] not in slots.get(r['slot'],{}).get('requirements','').split(','):
            bad['coverage'].append(r['requirement']+' unrealized port')
        elif type_tree(r['math-type'])!=ports[endpoint]:
            # At this layer nominal carriers are invariant: replacing one loses
            # required values and admits values from a foreign carrier.
            bad['missing'].append(r['requirement']+' widened/foreign carrier')
            bad['over'].append(r['requirement']+' excluded required carrier')
    bindings={}; mapping=set()
    for f in tables['FILLS']:
        mapping.add((f['path'],f['unit']))
        if f['slot'] not in slots:bad['fills'].append('unknown fill slot '+f['slot'])
        bindings.setdefault(f['slot'],set()).add(f['path']+':'+f['unit'])
        p=root/f['path']
        if not p.is_file() or f['unit'] not in units(p):bad['fills'].append('unit absent '+f['path']+':'+f['unit'])
    for s in S:
        for binding in filter(None,s['filled-by'].split(';')):
            if binding not in bindings.get(s['slot'],set()):bad['fills'].append('unmapped binding '+binding)
    # Constraints intersect independently on each requirement relation.
    for r in R:
        id=r['requirement']
        if id not in domains:continue
        universe,allowed,required=domains[id]; accepted=set(universe)
        cs=[c for c in C if c['requirement']==id]
        for c in cs:
            try:
                vals=set(json.loads(c['accepts']))
                if c['slot']!=r['slot'] or c['port']!=r['port'] or not vals<=universe:
                    bad['schema'].append(c['constraint']+' foreign relation')
                accepted &= vals
            except (ValueError,TypeError):bad['schema'].append(c['constraint']+' invalid relation')
        if accepted-allowed:bad['missing'].append('MISSING-CONSTRAINT '+id+': '+','.join(sorted(accepted-allowed)))
        if required-accepted:bad['over'].append('OVER-CONSTRAINT '+id+': '+','.join(sorted(required-accepted)))
    for c in C:
        if c['requirement'] not in reqs:bad['schema'].append('orphan constraint '+c['constraint'])
    subtract={(s['path'],s['unit']) for s in tables['SUBTRACT']}
    for s in tables['SUBTRACT']:
        p=root/s['path']; reference=mesh/'reference'/Path(s['path']).name
        if (s['path'],s['unit']) in mapping:bad['subtractions'].append('subtracted fill '+s['unit'])
        if not s['reason'] or not reference.is_file() or s['unit'] not in units(reference):bad['subtractions'].append('invalid removal '+s['unit'])
        if p.exists() and old_unit_present(p,reference,s['unit']):bad['subtractions'].append('seed still contains original '+s['path']+':'+s['unit'])
    for directory in ('plugin/makoto2','tests'):
        for p in sorted((root/directory).glob('*.py')):
            for unit in units(p):
                if (str(p.relative_to(root)),unit) not in mapping|subtract:bad['subtractions'].append('unclassified '+str(p)+':'+unit)
    try:
        from seed import measured_costs, task_class
        costs, floor = measured_costs(mesh/'COSTS.tsv')
        _, cost_tasks = read(root/'TASKS.tsv')
        for task in cost_tasks:
            minimum = costs.get(task_class(task['task']), floor)
            estimate = task['estimate_tokens']
            if not estimate.isdigit() or int(estimate) < minimum:
                bad['costs'].append(task['task']+' estimate below passing class floor '+str(minimum))
    except (OSError, KeyError, ValueError) as e:
        bad['costs'].append(str(e))
    # Route reflects every data dependency and every removal, no invented SCCs.
    try:
        header,tasks=read(root/'TASKS.tsv'); mh,rows=read(root/'MESH.tsv')
        taskmap={t['task']:t for t in tasks}; meshmap={m['hole']:m for m in rows}
        expected={'subtract','zero'} | (slots.keys()-{INPUT,OUTPUT})
        if header!=TASK_FIELDS or set(taskmap)!=expected or len(tasks)!=len(taskmap) or set(meshmap)!=expected:bad['route'].append('task/mesh coverage')
        for task in tasks:
            expected_check = 'PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/acceptance_tasks.py::test_'+task['task']
            if task['check'] != expected_check:bad['route'].append('non-product task check '+task['task'])
        completed=set(); remaining=set(taskmap)
        while remaining:
            ready={t for t in remaining if set(filter(None,taskmap[t]['deps'].split(',')))<=completed}
            if not ready:bad['route'].append('dependency cycle or missing task');break
            completed|=ready;remaining-=ready
        waves=[]; todo=set(taskmap); finished=set()
        while todo:
            ready=sorted(t for t in todo if set(filter(None,taskmap[t]['deps'].split(',')))<=finished)
            if not ready:break
            waves.append(ready);finished.update(ready);todo.difference_update(ready)
        plan=(root/'PLAN.md').read_text()
        for number,wave in enumerate(waves,1):
            cost=sum(int(taskmap[t]['estimate_tokens']) for t in wave)
            if f'Wave {number}: '+', '.join(wave)+f' (predicted {cost} tokens)' not in plan:bad['route'].append('stale plan wave '+str(number))
        for id,t in taskmap.items():
            if id in slots:
                required_scope = {'mesh/SLOTS.tsv', 'mesh/FILLS.tsv'}
                required_scope.update(f['path'] for f in tables['FILLS'] if f['slot'] == id)
                if id in {'validate','package','fresh','audit','join','handoff'}:
                    required_scope.add('plugin/makoto2/lifecycle.py')
                if not required_scope <= set(t['inputs'].split(',')):
                    bad['route'].append(id+' fill outside writable scope')
            need={'subtract'} if id not in ('subtract','zero') else set()
            if id in slots:
                need|=backward[id]-{INPUT,OUTPUT}
            if id=='zero':need|=slots.keys()-{INPUT,OUTPUT}
            if set(filter(None,t['deps'].split(',')))!=need:bad['route'].append(id+' incorrect dependencies')
            if not t['estimate_tokens'].isdigit() or int(t['estimate_tokens'])<=0 or 'PRESENT:' not in t['brief'] or 'ABSENT:' not in t['brief'] or 'EXTERNAL' not in t['brief'] or 're-measure' not in t['brief'] or 'BLOCKED' in t['brief']:bad['route'].append(id+' invalid prediction/cost/failure')
            sources = [(root / name).read_text() for name in SOURCE_PATHS]
            citation = meshmap.get(id, {}).get('citation', '')
            headings = {h for text in sources for h in re.findall(r'^#+ (.+)$', text, re.M)}
            if citation not in headings | {word['id'] for word in words}:
                bad['route'].append(id+' unresolved bare citation')
            m=meshmap.get(id,{})
            if m.get('check')!='PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py --task '+id or not m.get('plant'):bad['route'].append(id+' check/plant mismatch')
    except (OSError,KeyError,ValueError) as e:bad['route'].append(str(e))
    try:
        from tighten import render as fresh_tighten
        if (mesh/'TIGHTEN.tsv').read_text() != fresh_tighten(mesh):
            bad['tighten'].append('TIGHTEN.tsv differs from fresh deterministic fixpoint')
    except (OSError, ValueError, KeyError, TypeError) as e:
        bad['tighten'].append(str(e))
    return bad


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--only',choices=CHECKS);parser.add_argument('--task');args=parser.parse_args()
    bad=errors()
    if args.task:
        _,tasks=read(ROOT/'TASKS.tsv')
        if args.task not in {t['task'] for t in tasks}:parser.error('unknown task')
    selected=(args.only,) if args.only else CHECKS
    for c in selected:
        print(c+': '+('FAIL' if bad[c] else 'PASS'))
        for e in bad[c]:print('  '+e)
    return int(any(bad[c] for c in selected))

if __name__=='__main__':
    raise SystemExit(main())
