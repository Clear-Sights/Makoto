"""OTHER POINT: compare a subject to its recorded second reading.

Facts come from settled response fields or JSON response objects, never a
command's spelling. Unknown gate measurements are not invented.
"""
import ast
import json
import os
import re
import shlex


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


def _claims(event, reader, record=None):
    if record is None:
        return [dict(event['claim'])] if isinstance(event.get('claim'),dict) else []
    from makoto2.family_spec import read_claims
    return read_claims(record,event)


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
            if not isinstance(comp.key.args[0], ast.Name) or comp.key.args[0].id not in {n.id for n in ast.walk(gen.target) if isinstance(n, ast.Name)}:
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
        users = [i for i, e in enumerate(getattr(record, 'events', ()))
                 if e.get('hook_event_name') == 'UserPromptSubmit']
        if users and not any(o.seq > users[-1] and o.tool in ('Bash', 'Glob', 'Grep', 'Read') for o in record.obs):
            return [('B11', 'post-user probe')]
    if event.get('hook_event_name') != 'Stop':
        return []
    out = []
    for claim in _claims(event, reader, record):
        subject = claim.get('subject', '')
        if claim.get('kind') == 'clean' and subject and not any(o.input.get('command') == subject and o.exit is not None and o.exit != 0 for o in record.obs):
            out.append(('B4', subject))
        if (claim.get('helps') or claim.get('kind') == 'helps') and not any(isinstance(f.get('run_pair'), dict) and f['run_pair'].get('subject') == subject
               and 'with' in f['run_pair'] and 'without' in f['run_pair']
               and f['run_pair']['with'] != f['run_pair']['without'] for f in _facts(record)):
            out.append(('B14', subject))
    return out


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
        match = re.search(r'git\s+(checkout|switch|reset)\s+([^;\n&|]+)', ti.get('command', ''))
        if match:
            try:
                words = shlex.split(match[2])
            except ValueError:
                return []
            # Creating a branch does not select an unread existing revision.
            create = {'-b', '-B', '-c', '-C', '--create', '--force-create', '--orphan'}
            if any(w.split('=', 1)[0] in create for w in words):
                return []
            revision = next((w for w in words if not w.startswith('-')), None)
            if '--' in words and (revision is None or words.index('--') < words.index(revision)):
                return []  # checkout of paths, not a revision
            known = any(not o.failed and (revision in o.output or any(
                len(argv) > 3 and argv[0] == 'git' and argv[1] in ('checkout', 'switch')
                and any(flag in argv for flag in create) and revision in argv
                for argv, _ in reader._segments(o.input.get('command', ''))))
                for o in record.obs) if revision else False
            if revision and not known:
                return [('D12', revision)]
    return []


def other_plan(record, event, reader):
    if event.get('hook_event_name') != 'PreToolUse':
        return []
    if event.get('tool_name') != 'Bash':
        return []
    from makoto2.evaluate import OTHER_SESSION_TOOLS
    command = (event.get('tool_input') or {}).get('command','')
    instructions = {m.group(1) for o in record.obs if o.tool in OTHER_SESSION_TOOLS
                    for m in re.finditer(r'(?i)\brun\s+`([^`]+)`', o.output)}
    users = [e.get('prompt', '') for e in getattr(record, 'events', ())
             if e.get('hook_event_name') == 'UserPromptSubmit']
    return [command] if command in instructions and not any(command in text for text in users) else []


def other_claim(record, event, reader, dispatch=False):
    if event.get('hook_event_name') != 'Stop':
        return []
    out = []
    for c in _claims(event, reader, record):
        subject = c.get('subject', '')
        if c.get('kind') == 'running' and not any(subject in o.output for o in record.obs):
            out.append(('C8', subject))
        if c.get('kind') == 'done' and subject and not os.path.exists(reader._norm(subject, event.get('cwd', ''))):
            out.append(('D1', subject))
    if dispatch:
        for e in getattr(record, 'events', ()):
            if e.get('tool_name') != 'Agent':
                continue
            for command in re.findall(r'ACCEPTANCE:\s*(.+)', (e.get('tool_input') or {}).get('prompt', '')):
                if not any(o.input.get('command') == command and o.exit == 0 for o in record.obs):
                    out.append(('I3', command))
    return out


CHECKS = (('other_normalization', 'A14'), ('other_witness', 'B4,B11,B14'),
          ('other_run', 'D8,D14,F14'),
          ('other_write', 'D11,D12'),
          ('other_plan', 'F8,D13'))


def other_environment(record, event, reader):
    if event.get('hook_event_name') != 'PreToolUse' or event.get('tool_name') not in ('Write','Edit'):
        return []
    ti = event.get('tool_input') or {}
    text = ti.get('content', ti.get('new_string', ''))
    return [ti.get('file_path', '')] if re.search(r'if\s+os\.environ', text) else []


def findings(record, event, cfg):
    from makoto2 import observed as reader
    from makoto2.family_spec import finding
    for name, entries in CHECKS + (('other_environment', 'E7'),):
        check = globals()[name]
        for subject in check(record, event, reader):
            ids = entries
            if isinstance(subject, tuple):
                ids, subject = subject
            yield finding(ids.split(','), subject, check.__name__, 'OTHER.' + check.__name__)
    for entry, subject in other_claim(record, event, reader, cfg.get('dispatch', False)):
        yield finding(('C7','D1') if entry == 'D1' else (entry,), subject, 'other_claim', 'R11')
