"""OTHER POINT: compare a subject to its recorded second reading.

Facts come from settled response fields or JSON response objects, never a
command's spelling. Unknown gate measurements are not invented.
"""
import ast
import json
import os
import re


def _facts(record):
    for event in getattr(record, 'events', ()):
        if event.get('hook_event_name') not in ('PostToolUse', 'PostToolUseFailure'):
            continue
        response = event.get('tool_response')
        if isinstance(response, dict):
            yield response
            text = response.get('stdout', response.get('output', ''))
        else:
            text = response
        if isinstance(text, str):
            for line in text.splitlines():
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if isinstance(value, dict):
                    yield value


def _claims(event, reader):
    explicit = event.get('claim')
    if isinstance(explicit, dict):
        return [explicit]
    # Fixed word table; quoted examples and questions are not closing claims.
    result = []
    for line in reader.text_of(event).splitlines():
        if line.lstrip().startswith('>') or line.rstrip().endswith('?'):
            continue
        match = re.fullmatch(r'\s*(clean|running|done|plan|retracted)\s*:\s*(.+?)\s*', line, re.I)
        if match:
            result.append({'kind': match[1].lower(), 'subject': match[2]})
    return result


def _tree(text):
    try:
        return ast.parse(text)
    except (SyntaxError, TypeError):
        return None


def other_normalization(record, event, reader):
    ti = event.get('tool_input') or {}
    tree = _tree(ti.get('content', ti.get('new_string', '')))
    if event.get('hook_event_name') != 'PreToolUse' or tree is None:
        return []
    missing = []
    # Witness must follow the assignment in the same statement block and name
    # its input and output, not two unrelated cardinalities.
    for parent in ast.walk(tree):
        body = getattr(parent, 'body', None)
        if not isinstance(body, list):
            continue
        for i, node in enumerate(body):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            comp = node.value
            if not isinstance(comp, ast.DictComp) or not isinstance(comp.key, ast.Call):
                continue
            if len(comp.generators) != 1 or len(comp.key.args) != 1:
                continue
            gen = comp.generators[0]
            if ast.dump(comp.key.args[0]) != ast.dump(gen.target).replace('Store()', 'Load()'):
                continue
            wanted = {ast.dump(gen.iter), ast.dump(node.targets[0], include_attributes=False).replace('Store()', 'Load()')}
            witnessed = False
            for later in body[i+1:]:
                if not isinstance(later, ast.Assert):
                    continue
                test = later.test
                if not isinstance(test, ast.Compare) or len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
                    continue
                sides = [test.left, test.comparators[0]]
                if all(isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == 'len'
                       and len(x.args) == 1 and not x.keywords for x in sides):
                    witnessed |= {ast.dump(x.args[0]) for x in sides} == wanted
            if not witnessed:
                missing.append(ast.unparse(node.targets[0]))
    return missing


def other_witness(record, event, reader):
    if event.get('hook_event_name') == 'PreToolUse' and event.get('tool_name') == 'Agent':
        if not any(o.seq >= record.turn_start and o.tool in ('Bash', 'Glob', 'Grep', 'Read') for o in record.obs):
            return [('B11', 'post-user probe')]
    if event.get('hook_event_name') != 'Stop':
        return []
    out = []
    for claim in _claims(event, reader):
        subject = claim.get('subject', '')
        if claim.get('kind') == 'clean' and not any(o.input.get('command') == subject and o.exit is not None and o.exit != 0 for o in record.obs):
            out.append(('B4', subject))
        if claim.get('helps') and not any(isinstance(f.get('run_pair'), dict) and f['run_pair'].get('subject') == subject
               and 'with' in f['run_pair'] and 'without' in f['run_pair']
               and f['run_pair']['with'] != f['run_pair']['without'] for f in _facts(record)):
            out.append(('B14', subject))
    return out


def other_supervisor(record, event, reader):
    if event.get('launch') and not event.get('planted_event', {}).get('fires'):
        return ['planted launch event']
    return []


def other_run(record, event, reader):
    if event.get('hook_event_name') != 'Stop':
        return []
    out = []
    for f in _facts(record):
        run, shipped, real = f.get('run'), f.get('shipped'), f.get('real')
        if isinstance(run, dict):
            wrong_form = isinstance(shipped, dict) and 'form' in run and 'form' in shipped and run['form'] != shipped['form']
            small = isinstance(real, dict) and isinstance(run.get('size'), (int, float)) and isinstance(real.get('size'), (int, float)) and run['size'] < real['size']
            if wrong_form or small:
                out.append(('D8', str(run)))
        if run == 'suite' and 'git_status_after' in f and f['git_status_after'] != '':
            out.append(('D14', f['git_status_after']))
        pair, commit = f.get('ast'), f.get('commit')
        if isinstance(pair, dict) and isinstance(commit, dict) and re.search(r'no behaviou?r change', str(commit.get('message', ''))):
            old, new = _tree(pair.get('old')), _tree(pair.get('new'))
            if old is not None and new is not None and ast.dump(old) != ast.dump(new):
                out.append(('F14', commit['message']))
    return out


def other_write(record, event, reader):
    if event.get('hook_event_name') != 'PreToolUse':
        return []
    ti = event.get('tool_input') or {}
    if event.get('tool_name') == 'Write':
        path = reader._norm(ti.get('file_path', ''), event.get('cwd', ''))
        if path and os.path.exists(path):
            return [('D11', path)]
    if event.get('tool_name') == 'Bash':
        match = re.search(r'git\s+(checkout|switch|reset)\s+(\S+)', ti.get('command', ''))
        if match and not any(match[2] in o.output for o in record.obs):
            return [('D12', match[2])]
    return []


def other_drift(record, event, reader):
    from makoto2.lineage import unpaid
    return [name for state, name in unpaid(record, event, reader) if state == 'changed']


def other_refs(record, event, reader):
    from makoto2.lineage import unpaid
    return [name for state, name in unpaid(record, event, reader) if state == 'unread']


def other_edit(record, event, reader):
    if event.get('hook_event_name') != 'PreToolUse' or event.get('tool_name') != 'Edit':
        return []
    ti = event.get('tool_input') or {}
    new = ti.get('new_string')
    edits = [o for o in record.obs if o.tool == 'Edit' and o.input.get('new_string') == new]
    if not edits or not any(reader._norm(o.input.get('file_path', ''), event.get('cwd', '')) != reader._norm(ti.get('file_path', ''), event.get('cwd', '')) for o in edits):
        return []
    failed = {o.input.get('command') for o in record.obs if o.exit is not None and o.exit != 0}
    if not any(o.seq > edits[-1].seq and o.input.get('command') in failed and o.exit is not None for o in record.obs):
        return [str(new)]
    return []


def other_plan(record, event, reader):
    if event.get('hook_event_name') != 'Stop':
        return []
    claims = [c for e in getattr(record, 'events', ()) for c in _claims(e, reader)]
    planned = {c.get('subject') for c in claims if c.get('kind') == 'plan'}
    settled = {c.get('subject') for c in claims if c.get('kind') in ('done', 'retracted')}
    return sorted(planned - settled)


def other_claim(record, event, reader, dispatch=False):
    if event.get('hook_event_name') != 'Stop':
        return []
    out = []
    for c in _claims(event, reader):
        subject = c.get('subject', '')
        if c.get('kind') == 'running' and not any(subject in o.output for o in record.obs):
            out.append(('C8', subject))
        if c.get('kind') == 'done' and not os.path.exists(reader._norm(subject, event.get('cwd', ''))):
            out.append(('D1', subject))
    if dispatch:
        for e in getattr(record, 'events', ()):
            if e.get('tool_name') != 'Agent':
                continue
            for command in re.findall(r'ACCEPTANCE:\s*(.+)', (e.get('tool_input') or {}).get('prompt', '')):
                if not any(o.input.get('command') == command and o.exit == 0 for o in record.obs):
                    out.append(('I3', command))
    return out


CHECKS = ((other_normalization, 'A14'), (other_witness, 'B4,B11,B14'),
          (other_supervisor, 'B26,B1,D9'), (other_run, 'D8,D14,F14'),
          (other_write, 'D11,D12'), (other_edit, 'F2,H3'),
          (other_plan, 'F8,D13'))


def findings(record, event, reader, dispatch=False):
    for check, entries in CHECKS:
        for subject in check(record, event, reader):
            if isinstance(subject, tuple):
                entries, subject = subject
            yield {'row': 'OTHER.' + check.__name__, 'message': entries + ': ' + str(subject), 'objects': [str(subject)]}
    for entries, subject in other_claim(record, event, reader, dispatch):
        yield {'row': 'R11', 'message': entries + ': ' + str(subject), 'objects': [str(subject)]}
