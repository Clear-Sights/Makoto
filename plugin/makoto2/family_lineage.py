"""LINEAGE: the register's predicates over readings before the current write.

Source identities are paths, URLs, complete SHAs, and quoted values. Reader
metadata carries cwd and explicit source/verifier witnesses without inferring
facts from an agent's answer. No entry names participate in the predicates.
"""
import ast
import hashlib
import os
import re


def digest(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def anchor(name, cwd, reader):
    # _norm joins only onto a '/'-rooted cwd; a drive-rooted cwd is absolute too.
    if (cwd and os.path.isabs(cwd) and not cwd.startswith('/') and not os.path.isabs(name)
            and '://' not in name and not reader._RATIO_RX.fullmatch(name)):
        return reader._norm(os.path.join(cwd, name), '')
    return name


def references(text, cwd, reader):
    text = re.sub(r'(?<=\w)\.(?=\s|$)', '', str(text or ''))
    refs = {anchor(p.rstrip('.!?'), cwd, reader) for p in reader._text_objects(text, cwd)
            if '://' in p or '/' in p or '.' in os.path.basename(p)}
    refs.update(m.group(1) for m in re.finditer(r'(?i)\b(?:commit|revision|sha)\s+([0-9a-f]{7,64})(?![\w])', text)
                if re.search('[a-f]', m.group(1)))
    refs.update(m.group(0) for m in re.finditer(r'(?<![\w])[0-9a-f]{40}(?:[0-9a-f]{24})?(?![\w])', text))
    for match in re.finditer(r'"([^"\n]+)"|“([^”\n]+)”', text):
        value = match.group(1) or match.group(2)
        # A quoted path has the same identity as its unquoted spelling.
        named = reader._text_objects(value, cwd)
        refs.add(anchor(next(iter(named)), cwd, reader) if len(named) == 1 else value)
    return refs


def readings(record, reader):
    sources, owned = {}, set()
    for obs in record.obs:
        if obs.failed:
            continue
        owned.update(obs.written | obs.created)
        meta = getattr(record, 'reader_evidence', {}).get(obs.seq, {})
        cwd = meta.get('cwd', '')
        # Only the source reader tools (or an explicit source witness) pay.
        identities = set(meta.get('source_reads', ()))
        if obs.tool == 'Read':
            path = obs.input.get('file_path')
            if path:
                identities.add(reader._norm(path, cwd))
            if obs.input.get('ref'):
                identities.add(obs.input['ref'])
        elif obs.tool == 'Bash':
            segments = list(reader._segments(obs.input.get('command', '')))
            if len(segments) == 1:
                argv, op = segments[0]
                if len(argv) == 2 and os.path.basename(argv[0]) == 'cat' and not argv[1].startswith('-'):
                    identities.add(reader._norm(argv[1], cwd))
        elif obs.tool == 'WebFetch' and obs.input.get('url'):
            identities.add(obs.input['url'])
        # Explicit identity fields in settled measurements are primary witnesses,
        # including benchmark revisions; their format is independent of tool names.
        if obs.tool == 'Bash':
            for sha in re.findall(r'\b(?:revision|commit|sha(?:256)?)\s*[:=]\s*([0-9a-f]{7,64})(?![\w])', obs.output):
                sources[sha] = digest(sha)
        # git log/show are primary readings of commit identities, not relays.
        if obs.tool == 'Bash' and any(len(argv) >= 2 and argv[0] == 'git'
                and argv[1] in ('log', 'show')
                for argv, _ in reader._segments(obs.input.get('command', ''))):
            for sha in re.findall(r'(?m)^(?:commit\s+)?([0-9a-f]{7,64})(?=\s|$)', obs.output):
                sources[sha] = digest(sha)
        # ls-remote is a primary reading of remote refs, including their SHA.
        if obs.tool == 'Bash' and any('ls-remote' in argv and 'git' in argv
                for argv, _ in reader._segments(obs.input.get('command', ''))):
            for sha, ref in re.findall(r'(?m)^([0-9a-f]{40})\s+(refs/heads/\S+)\s*$', obs.output):
                sources[sha] = digest(sha)
                for size in range(7, 40):
                    sources[sha[:size]] = digest(sha[:size])
                sources[reader._norm(ref.removeprefix('refs/heads/'), cwd)] = digest(sha)
        for name in identities:
            if name not in owned:
                sources[name] = digest(obs.output)
        # A quoted value is backed by an actual source's content, not a relay.
        if identities:
            sources[obs.output] = digest(obs.output)
            for name in references(obs.output, cwd, reader):
                if not ('/' in name or '.' in os.path.basename(name)):
                    sources[name] = digest(name)
    return sources, owned


def output_text(event, reader):
    if event.get('hook_event_name') in ('Stop', 'SubagentStop'):
        return reader.text_of(event)
    ti = event.get('tool_input') or {}
    if event.get('tool_name') in ('Write', 'Edit', 'MultiEdit'):
        return ti.get('content', ti.get('new_string', ''))
    # refs(output) is Write/Edit content or closing text (register definition).
    return ''


def cited_references(event, reader):
    """References used as evidence, rather than strings naming future artifacts.

    Bare path lists remain supported by unpaid() for ledger clients. Hook
    decisions require a citation/dependency context. Written local dependencies
    must exist; a proposed output name is not an unread source.
    """
    text = output_text(event, reader)
    cwd = event.get('cwd') or ''
    if (event.get('hook_event_name') != 'PreToolUse'
            or event.get('tool_name') not in ('Write', 'Edit')
            or not str((event.get('tool_input') or {}).get('file_path', '')).endswith('.py')):
        # Explicit citation relationships differ from proposed output names and
        # reminder lists. Only the cited referent incurs the reading obligation.
        refs = references(text, cwd, reader)
        return {name for name in refs if
                re.search(r'(?i)\b(?:commit|revision|sha)\s+' + re.escape(name) + r'(?!\w)', text)
                or re.search(r'(?i)\b(?:according to|source:|cites?|by|from)\s+`?'
                    + re.escape(os.path.basename(name)) + r'(?![\w.-])', text)
                or re.search(re.escape(os.path.basename(name)) + r'`?\s+(?:says|states)\b', text, re.I)}
    selected = set()
    try:
        tree = ast.parse(text)
    except (SyntaxError, TypeError):
        return set()
    for node in ast.walk(tree):
        modules = ([a.name for a in node.names] if isinstance(node, ast.Import)
                   else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
        for module in modules:
            for suffix in ('.py','/__init__.py'):
                name = reader._norm(module.replace('.', '/') + suffix, cwd)
                if os.path.isfile(name):
                    selected.add(name)
    return selected


def hook_lineage_refs(record, event, reader):
    sources, owned = readings(record, reader)
    cwd = event.get('cwd') or ''
    own = reader._norm((event.get('tool_input') or {}).get('file_path', ''), cwd)
    return sorted(n for n in cited_references(event, reader) - owned - {own}
                  if n not in sources)


def lineage_refs(record, event, reader):
    sources, owned = readings(record, reader)
    cwd = event.get('cwd') or ''
    refs = references(output_text(event, reader), cwd, reader)
    refs.update(event.get('refs') or ())
    own = reader._norm((event.get('tool_input') or {}).get('file_path', ''), cwd)
    refs.difference_update(owned | {own})
    return sorted(name for name in refs if name not in sources
                  and not (not os.path.isabs(name) and '://' not in name
                           and not re.fullmatch('[0-9a-f]{40}(?:[0-9a-f]{24})?', name)
                           and any(name in o.output for o in record.obs
                              if not o.failed and (o.tool in ('Read', 'WebFetch')
                                  or getattr(record, 'reader_evidence', {}).get(o.seq, {}).get('source_reads')))))


def lineage_drift(record, event, reader):
    sources, owned = readings(record, reader)
    cwd = event.get('cwd') or ''
    refs = references(output_text(event, reader), cwd, reader) | set(event.get('refs') or ())
    own = reader._norm((event.get('tool_input') or {}).get('file_path', ''), cwd)
    changed = []
    for name in sorted(refs - owned - {own}):
        if name not in sources:
            continue  # missing readings belong to lineage_refs
        # A remote branch ref is not a local file with the same spelling.
        if any(o.tool == 'Bash' and not o.failed
               and any('ls-remote' in argv and 'git' in argv
                       for argv, _ in reader._segments(o.input.get('command', '')))
               and any(name == reader._norm(ref.removeprefix('refs/heads/'),
                       getattr(record, 'reader_evidence', {}).get(o.seq, {}).get('cwd', ''))
                       for ref in re.findall(r'(?m)^[0-9a-f]{40}\s+(refs/heads/\S+)\s*$', o.output))
               for o in record.obs):
            continue
        tree = event.get('tree') or {}
        if name in tree:
            current = tree[name].get('hash') if isinstance(tree[name], dict) else tree[name]
        elif '://' in name or re.fullmatch('[0-9a-f]{40}(?:[0-9a-f]{24})?', name):
            # No current remote reading is available offline.
            continue
        elif name in sources and not ('/' in name or '.' in os.path.basename(name)):
            continue  # quoted values carry their own immutable identity
        else:
            path = name if os.path.isabs(name) else os.path.join(cwd, name)
            try:
                with open(path, encoding='utf-8') as source:
                    current = digest(source.read())
            except FileNotFoundError:
                # A receipt cannot verify a local source that is no longer
                # available. An explicitly unverified reference makes no claim
                # to current source bytes.
                if re.search(r'\bunverified\b', output_text(event, reader), re.I):
                    continue
                current = None
            except OSError:
                continue  # Unavailable reading cannot establish a changed hash.
        if current != sources[name]:
            changed.append(name)
    return changed


def lineage_absence(record, event, reader):
    # Semantic absence of a falsifier has no deterministic native witness.
    return []




def lineage_units(record, event, reader):
    if event.get('hook_event_name') != 'PreToolUse':
        return []
    ti = event.get('tool_input') or {}
    path = ti.get('file_path', '')
    if not path.endswith('.py'):
        return []
    code = ti.get('content')
    if event.get('tool_name') == 'Edit':
        try:
            with open(reader._norm(path, event.get('cwd') or ''), encoding='utf-8') as source:
                old = source.read()
            code = old.replace(ti.get('old_string', ''), ti.get('new_string', ''),
                               -1 if ti.get('replace_all') else 1)
        except OSError:
            return []
    if not isinstance(code, str):
        return []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    sources, owned = readings(record, reader)
    # An ordinary implementation session does not declare a closed claim
    # inventory. Without one, orphanhood is not evaluable from a missing comment.
    claim_texts = [o.output for o in record.obs if not o.failed
                   and o.tool == 'Read' and any(n in sources for n in o.objects)
                   and re.search(r'(?im)^#+\s*(?:requirements|claims|contract)\b', o.output)]
    if not claim_texts:
        return []
    units = []
    lines = code.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.decorator_list or node.name.startswith('test_'):
            continue
        claim = ast.get_docstring(node) or ''
        claim += '\n' + '\n'.join(line.split('#', 1)[1] for line in lines[node.lineno-1:node.end_lineno] if '#' in line)
        refs = references(claim, event.get('cwd') or '', reader)
        named = any(re.search(r'(?<!\w)' + re.escape(node.name) + r'(?!\w)', text)
                    for text in claim_texts)
        backed = bool(refs & sources.keys())
        if not named and not backed:
            units.append(node.name)
    return units


def lineage_pin(args, cfg, record, event):
    prompt = (event.get('tool_input') or {}).get('prompt', '')
    if (not cfg.get('dispatch') or event.get('tool_name') != 'Agent'
            or event.get('hook_event_name') != 'PreToolUse' or not isinstance(prompt, str)):
        return []
    return ['READ'] if re.search(r'(?m)^READ:', prompt) and not re.search(r'(?m)^READ:.*@[0-9a-f]{12,}', prompt) else []


def unpaid(record, event, reader):
    if event.get('hook_event_name') not in ('PreToolUse', 'Stop', 'SubagentStop'):
        return []
    return [('unread', n) for n in lineage_refs(record, event, reader)] + [('changed', n) for n in lineage_drift(record, event, reader)]


def lineage_edit(record, event, reader):
    from makoto2.family_spec import history, args, verifier_keys, is_verifier
    if event.get('hook_event_name') != 'PreToolUse' or event.get('tool_name') != 'Edit':
        return []
    new = args(event).get('new_string')
    # Importing the same owner in two consumers unifies the rule; copying
    # an implementation duplicates it. This distinction is structural.
    try:
        tree = ast.parse(new or '')
    except (SyntaxError, TypeError):
        tree = None
    if tree is not None and tree.body and all(isinstance(n, (ast.Import, ast.ImportFrom)) for n in tree.body):
        return []
    path = reader._norm(args(event).get('file_path', ''), event.get('cwd', ''))
    events = history(record)
    edits = [i for i, e in enumerate(events) if e.get('tool_name') == 'Edit'
             and args(e).get('new_string') == new]
    if not edits or not any(reader._norm(args(events[i]).get('file_path', ''),
                            events[i].get('cwd', event.get('cwd', ''))) != path for i in edits):
        return []
    keys = verifier_keys(record)
    return [] if any(is_verifier(e, keys) for e in events[edits[-1]+1:]) else [path]


def findings(record, event, cfg):
    from makoto2 import observed as reader
    from makoto2.family_spec import finding
    if event.get('hook_event_name') not in ('PreToolUse','Stop','SubagentStop'):
        return
    checks = (
        (lineage_absence, ('C2','B32'), 'R05'),
        (hook_lineage_refs, ('A2','G1','H1','H4','H5'), 'R08'),
        (lineage_drift, ('D4','F7','F10','H2'), 'L.drift'),
        (lineage_edit, ('F2','H3'), 'L.edit'),
        (lineage_units, ('H6',), 'L.units'),
    )
    for check, entries, row in checks:
        subjects = check(record, event, reader)
        if subjects is True:
            subjects = ['claim']
        for subject in subjects or ():
            yield finding(entries, subject, check.__name__ + ' -- source: REGISTER.md (origin REGISTRY-v9.md)', row)
