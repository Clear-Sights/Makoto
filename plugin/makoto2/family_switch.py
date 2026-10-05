"""SWITCH: supply a subject/input, then read its tree or executed response.

These functions are the family boundary for the serialized integrator in PLAN.md.
No command-name heuristic supplies run, plant, settings, or removal evidence.
"""
import ast
import re


def switch_tree(source):
    """Return literal tree defects with their source locations."""
    tree = ast.parse(source)
    out = []
    def emit(predicate, node):
        out.append((predicate, node.lineno))
    for node in ast.walk(tree):
        if isinstance(node, ast.IfExp):
            branches = (node.body, node.orelse)
            if (all(isinstance(x, ast.Constant) and type(x.value) is int and x.value in (0, 1)
                    for x in branches) and re.search(r'>=\s*0?\.\d+', ast.get_source_segment(source, node.test) or '')):
                emit('gradient', node)
        elif isinstance(node, ast.Match):
            last = node.cases[-1]
            if not (isinstance(last.pattern, ast.MatchAs) and last.pattern.pattern is None
                    and last.pattern.name is None and last.guard is None
                    and last.body and isinstance(last.body[-1], ast.Raise)):
                emit('fallthrough', node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}
            # Count loads only in the enclosing lexical scope, not in unrelated defs.
            scope = tree
            for candidate in ast.walk(tree):
                if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node in list(ast.walk(candidate)):
                    scope = candidate
            loads = {n.id for n in ast.walk(scope) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
            if names and not names & loads:
                emit('unused_result', node)
        elif isinstance(node, (ast.Try, ast.TryStar)):
            calls = {ast.dump(n, include_attributes=False) for stmt in node.body for n in ast.walk(stmt) if isinstance(n, ast.Call)}
            for handler in node.handlers:
                recovery = {ast.dump(n, include_attributes=False) for stmt in handler.body for n in ast.walk(stmt) if isinstance(n, ast.Call)}
                if calls and calls <= recovery:
                    emit('recovery', handler)
    return out


def switch_self(launch, plant, feed):
    """Feed the planted event to the actual checker; read whether it fires."""
    return bool(launch and not feed(plant))


def switch_run(response):
    """Read a settled run response, retaining each independent failed predicate."""
    out = []
    if response.get('run') == 'suite_on_clean_base' and any(v != 0 for v in response['checks'].values()):
        out.append('clean_base')
    if response.get('run') == 'plant' and set(response['reddened_rows']) != {response['plant']}:
        out.append('isolated_row')
    if response.get('run') == 'suite' and not response['replay_sequence']:
        out.append('replay_sequence')
    if response.get('run') == 'gate_on_own_tree' and response['verdict'] != 'pass':
        out.append('own_tree')
    if 'shipped' in response and response['shipped'] != response['tested']:
        out.append('settings')
    if response.get('run') == 'gate' and response.get('exitCode', 0) != 0:
        out.append('crash')
    if response.get('run') == 'removals' and isinstance(response.get('before'), list):
        before = set(response['before'])
        for removal in response.get('removals', ()):
            after = set(removal['after'])
            if before == after and 'simpler' not in out:
                out.append('simpler')
            if (before ^ after) - {removal['term']} and 'unrelated' not in out:
                out.append('unrelated')
    return out


def switch_write(event, test_path):
    """B2/B5/B20 share this exact content predicate."""
    return (event.get('event') == 'Pre' and event.get('tool') in {'Write', 'Edit'}
            and re.search(test_path, event.get('path', '')) is not None
            and re.search(r'\b(assert|raise|expect)', event.get('content', '')) is None)


def switch_zero(units, read, terms, shape=0):
    """Execute every single-unit removal and compare the actual met row sets."""
    units = tuple(units)
    before = set(read(units))
    redundant, unrelated = [], []
    for i, unit in enumerate(units):
        after = set(read(units[:i] + units[i + 1:]))
        if before == after:
            redundant.append(unit)
        if (before ^ after) - {terms[unit]}:
            unrelated.append(unit)
    return {'simpler': bool(redundant or shape > 0), 'unrelated': bool(unrelated),
            'redundant_units': redundant, 'unrelated_units': unrelated}


def switch_exit(checks, subject):
    """The gate's own invocations decide; exceptions resolve as denial."""
    exits = []
    for check in checks:
        try:
            response = check(subject)
            code = response.returncode
        except Exception:
            code = 1
        exits.append(code)
    return exits


def switch_pass(event, observations):
    """C3/A7: a named passing command requires its observed zero exit."""
    claim = event.get('claim', {})
    return (event.get('event') == 'Stop' and claim.get('kind') == 'pass'
            and not any(o.get('exit') == 0 and re.search(claim['subject'], o.get('command', ''))
                        for o in observations))


def switch_doc(event, observations, doc_path):
    """Use the register's seen(verifier), including a failed verifier."""
    return (event.get('event') == 'Pre' and event.get('tool') in {'Write', 'Edit'}
            and event.get('claim', {}).get('kind') == 'pass'
            and re.search(doc_path, event.get('path', '')) is not None
            and not any(o.get('verifier') for o in observations))


def findings(record, event, cfg):
    """Read native hook inputs and explicit settled run responses at the boundary."""
    from makoto2.family_other import _facts
    ti=event.get('tool_input') or {}
    if (event.get('hook_event_name')=='PreToolUse' and event.get('tool_name') in ('Write','Edit')
            and str(ti.get('file_path','')).endswith('.py')):
        source=ti.get('content',ti.get('new_string',ti.get('new','')))
        try:
            defects=switch_tree(source)
        except (SyntaxError,TypeError,ValueError):
            defects=[]
        entries={'gradient':'A6','fallthrough':'C5','unused_result':'E1','recovery':'E9'}
        for predicate,line in defects:
            yield {'row':'SWITCH.'+predicate,'entries':[entries[predicate]],'message':entries[predicate]+': '+predicate,'objects':[str(ti.get('file_path','')),str(line)]}
    if event.get('hook_event_name') == 'PreToolUse' and event.get('tool_name') in ('Write','Edit'):
        from makoto2.family_spec import read_claims,verifier_keys
        doc_paths=cfg.get('named_sets',{}).get('DOC_PATH',())
        observations=[{'verifier':o.input.get('command') in verifier_keys(record)} for o in record.obs]
        for claim in read_claims(record,event):
            adapted={'event':'Pre','tool':event.get('tool_name'),'path':ti.get('file_path',''),'claim':claim}
            if any(switch_doc(adapted,observations,path) for path in doc_paths):
                yield {'row':'SWITCH.doc','entries':['C11'],'message':'C11: no verifier seen','objects':[adapted['path']]}
    if event.get('hook_event_name') == 'Stop':
        from makoto2 import observed
        from makoto2.family_spec import finding
        for response in _facts(record):
            for subject in switch_supervisor(record, response, observed):
                yield finding(('B1','D9','B26'), subject, 'switch_supervisor', 'SWITCH.supervisor')
    if event.get('hook_event_name')=='Stop':
        entries={'crash':'C4','simpler':'B37','unrelated':'F6','clean_base':'B10','isolated_row':'B21','replay_sequence':'B28','own_tree':'B34','settings':'E8'}
        required={'suite_on_clean_base':('checks',),'plant':('reddened_rows','plant'),
                  'suite':('replay_sequence',),'gate_on_own_tree':('verdict',)}
        for response in _facts(record):
            run=response.get('run')
            needs=required.get(run,()) if isinstance(run,str) else ()
            if any(k not in response for k in needs) or ('shipped' in response and 'tested' not in response):
                continue
            for predicate in switch_run(response):
                yield {'row':'SWITCH.'+predicate,'entries':[entries[predicate]],'message':entries[predicate]+': '+predicate,'objects':[str(response)]}

def switch_supervisor(record, event, reader):
    if event.get('launch') and not event.get('planted_event', {}).get('fires'):
        return ['planted launch event']
    return []
