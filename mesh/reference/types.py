"""Conservative AST extraction. Unresolved is a proof obligation, never a type.
No runtime imports, hooks, or evaluation. Stable IDs use lexical name and call ordinal.
"""
import sys
if __name__ == '__main__':
    sys.path.pop(0)
import ast
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = 'plugin/makoto2/*.py'
SLOT_FIELDS = ['slot', 'inputs:type', 'outputs:type', 'multiplicity', 'loosest-interpretation', 'filled-by']
WIRE_FIELDS = ['from-slot.output', 'to-slot.input', 'type']

def annotation(node):
    if node is None:
        return 'UNRESOLVED'
    value = ast.unparse(node)
    if re.search(r'\b(dict|list|tuple|set|frozenset|Iterable|Optional)\b(?!\[)', value) or 'Any' in value:
        return 'UNRESOLVED'
    return value

def return_type(node):
    declared = annotation(getattr(node, 'returns', None))
    if declared != 'UNRESOLVED':
        return declared
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.body or not isinstance(node.body[-1], ast.Return):
        return 'UNRESOLVED'
    returns=[]
    def walk(n):
        for child in ast.iter_child_nodes(n):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, (ast.Yield, ast.YieldFrom)):
                returns.append('UNRESOLVED')
            if isinstance(child, ast.Return):
                value=child.value
                if value is None: returns.append('NoneType')
                elif isinstance(value,ast.Constant): returns.append(type(value.value).__name__)
                elif isinstance(value,ast.Compare) or isinstance(value,ast.UnaryOp) and isinstance(value.op,ast.Not): returns.append('bool')
                else: returns.append('UNRESOLVED')
            walk(child)
    walk(node)
    return returns[0] if returns and len(set(returns))==1 else 'UNRESOLVED'

def extract(root=ROOT):
    slots, wires = {}, []
    def slot(name, unit, ins=None, outs=None):
        slots[name] = {'slot': name, 'inputs:type': ins or {}, 'outputs:type': outs or {},
                       'multiplicity': 'one invocation; loops zero-or-many; branches zero-or-one',
                       'loosest-interpretation': 'inhabited values satisfying proven annotations; unresolved ports remain EMPTY',
                       'filled-by': unit}
    def wire(a, ap, b, bp, typ):
        slots[a]['outputs:type'][ap] = typ
        slots[b]['inputs:type'].setdefault(bp, typ)
        wires.append(dict(zip(WIRE_FIELDS, [a+'#'+ap, b+'#'+bp, typ])))
    units = []
    for path in sorted(root.glob(SOURCES)):
        rel = str(path.relative_to(root)); tree = ast.parse(path.read_text())
        prefix = path.stem
        definitions = {}
        def visit(node, parent):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    name = parent+'.'+(child.name if hasattr(child, 'name') else 'lambda@'+str(child.lineno)+':'+str(child.col_offset))
                    definitions[id(child)] = name
                    visit(child, name)
                elif isinstance(child, ast.ClassDef):
                    visit(child, parent+'.'+child.name)
                else:
                    visit(child, parent)
        visit(tree, prefix)
        module = prefix+'.<module>'
        slot(module, rel+':<module>', {'start': 'Unit'}, {'done': 'Unit'})
        units.append((module, tree, rel, definitions))
        for node in ast.walk(tree):
            if id(node) not in definitions: continue
            name = definitions[id(node)]
            args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            ins = {a.arg: annotation(a.annotation) for a in args}
            for a in (node.args.vararg, node.args.kwarg):
                if a: ins[a.arg] = 'UNRESOLVED'
            slot(name, rel+':'+name, ins, {'return': return_type(node)})
            units.append((name, node, rel, definitions))
    functions = set(slots)
    def body_calls(node):
        def walk(n):
            for c in ast.iter_child_nodes(n):
                if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue
                if isinstance(c, ast.Call): yield c
                yield from walk(c)
        return list(walk(node))
    for owner, node, rel, definitions in units:
        for index, call in enumerate(body_calls(node)):
            spelling = ast.unparse(call.func)
            # Attribute dispatch, importlib and callback aliases need proof, not guesses.
            candidates = [owner.rsplit('.',1)[0]+'.'+spelling, owner.split('.')[0]+'.'+spelling, spelling]
            target = next((x for x in candidates if x in functions), None)
            if target is None:
                target = owner+'.call'+str(index)+'.'+spelling
                slot(target, 'EMPTY', {}, {'return':'UNRESOLVED'})
            wire(owner, 'call'+str(index)+'.invoke', target, 'invoke', 'Unit')
            inputs = [p for p in slots[target]['inputs:type'] if p != 'invoke']
            def expression_type(expr):
                if isinstance(expr, ast.Constant):
                    return type(expr.value).__name__
                if isinstance(expr, ast.Name):
                    return slots[owner]['inputs:type'].get(expr.id, 'UNRESOLVED')
                return 'UNRESOLVED'
            for i, arg in enumerate(call.args):
                port = inputs[i] if i < len(inputs) else 'arg'+str(i)
                typ = expression_type(arg)
                if port not in slots[target]['inputs:type']: slots[target]['inputs:type'][port]='UNRESOLVED'
                wire(owner, 'call'+str(index)+'.arg'+str(i), target, port, typ)
            for kw in call.keywords:
                port = kw.arg or '**kwargs'
                typ = expression_type(kw.value)
                if port not in slots[target]['inputs:type']: slots[target]['inputs:type'][port]='UNRESOLVED'
                wire(owner, 'call'+str(index)+'.kw.'+port, target, port, typ)
            wire(target, 'return', owner, 'call'+str(index)+'.result', slots[target]['outputs:type']['return'])
    slot('PROGRAM_INPUT', 'EMPTY', {}, {'start':'Unit'})
    slot('PROGRAM_OUTPUT', 'EMPTY', {'done':'Unit'}, {})
    hooks=json.loads((root/'plugin/hooks/hooks.json').read_text())['hooks']
    commands=sorted({entry['command'] for events in hooks.values() for event in events for entry in event['hooks'] if entry['type']=='command'})
    command_type='Literal['+','.join(repr(command) for command in commands)+']'
    slot('INPUT.hook-command','EMPTY',{'request':'Unit'},{'value':command_type})
    slot('shell.entry', 'plugin/hooks/hooks.json:command:'+json.dumps(commands), {'payload':'UNRESOLVED','start':'Unit'}, {'stdout':'UNRESOLVED','done':'Unit'})
    wire('PROGRAM_INPUT','hook-command','INPUT.hook-command','request','Unit')
    wire('INPUT.hook-command','value','shell.entry','command',command_type)
    wire('PROGRAM_INPUT','start','shell.entry','start','Unit')
    wire('shell.entry','invoke','__main__.<module>','start','Unit')
    wire('__main__.<module>','done','shell.entry','done','Unit')
    wire('shell.entry','stdout','PROGRAM_OUTPUT','stdout','UNRESOLVED')
    for owner,node,rel,definitions in units:
        if not owner.endswith('<module>'): continue
        for imported in ast.walk(node):
            if isinstance(imported,ast.ImportFrom) and imported.module=='makoto2':
                for alias in imported.names:
                    target=alias.name+'.<module>'
                    if target in slots:
                        wire(owner,'import.'+alias.name,target,'start','Unit')
                        wire(target,'done',owner,'imported.'+alias.name,'Unit')
                wire(owner,'import.package','__init__.<module>','start','Unit')
                wire('__init__.<module>','done',owner,'imported.package','Unit')
    for label, consumer, port in [('stdin','shell.entry','payload'),('environment','__main__.run','environment'),('configuration','evaluate.load_cfg','file'),('rule-table','evaluate.load_rows','file'),('session-state','hook.sigma_read','file')]:
        slot('INPUT.'+label,'EMPTY',{'request':'Unit'},{'value':'UNRESOLVED'})
        wire('PROGRAM_INPUT',label,'INPUT.'+label,'request','Unit')
        wire('INPUT.'+label,'value',consumer,port,'UNRESOLVED')
    slot('OUTPUT.session-state','EMPTY',{'value':'UNRESOLVED'},{'done':'Unit'})
    wire('hook.sigma_append','state-effect','OUTPUT.session-state','value','UNRESOLVED')
    wire('OUTPUT.session-state','done','PROGRAM_OUTPUT','state-written','Unit')
    wire('__main__.<module>','done','PROGRAM_OUTPUT','done','Unit')
    return [slots[k] for k in sorted(slots)], sorted(wires, key=lambda w: tuple(w.values()))

def write(root=ROOT):
    slots, wires = extract(root)
    for filename, fields, rows in [('SLOTS.tsv', SLOT_FIELDS, slots), ('WIRES.tsv', WIRE_FIELDS, wires)]:
        with (root/'mesh'/filename).open('w') as f:
            writer = csv.DictWriter(f, fields, delimiter='\t', lineterminator='\n'); writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v, sort_keys=True, separators=(',',':')) if isinstance(v,dict) else v for k,v in row.items()})

if __name__ == '__main__':
    write()
