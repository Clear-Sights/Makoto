"""REGISTER v9:13-16: source readings, reference names, and hash drift.

The record is rebuilt from settled observations. Names in an answer do not
create source readings, and reading content written by this session does not
turn that content into an independent source.
"""
import hashlib
import os


def digest(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def readings(record, reader):
    sources, owned = {}, set()
    for obs in record.obs:
        if obs.failed:
            continue
        owned.update(obs.written | obs.created)
        path = obs.input.get('file_path') if obs.tool == 'Read' else None
        if path:
            names = [reader._norm(path, '')]
            names.extend(p for p in obs.objects if p.endswith('/' + path.lstrip('./')) or p == path)
            for name in names:
                if name not in owned:
                    sources[name] = digest(obs.output)
    return sources, owned


def unpaid(record, event, reader):
    """Every named source must have been read; local sources must remain current."""
    tool = event.get('tool_name')
    closing = event.get('hook_event_name') in ('Stop', 'SubagentStop')
    if not closing and tool not in ('Write', 'Edit', 'MultiEdit'):
        return []
    ti = event.get('tool_input') or {}
    text = reader.text_of(event) if closing else ti.get('content', ti.get('new_string', ''))
    cwd = event.get('cwd') or ''
    refs = reader._text_objects(str(text), cwd)
    refs = {p for p in refs if '/' in p or '.' in os.path.basename(p)}
    own = reader._norm(ti.get('file_path', ''), cwd)
    refs.discard(own)
    sources, owned = readings(record, reader)
    missing = []
    for name in sorted(refs):
        # Identity includes cwd; a relative read and reference resolve to the same name.
        candidates = [name]
        if cwd and name.startswith(cwd.rstrip('/') + '/'):
            candidates.append(os.path.relpath(name, cwd))
        prior = next((sources[p] for p in candidates if p in sources), None)
        if prior is None:
            missing.append(('unread', name))
            continue
        if not cwd or '://' in name:
            continue
        path = name if os.path.isabs(name) else os.path.join(cwd, name)
        try:
            with open(path, encoding='utf-8') as source:
                current = digest(source.read())
        except OSError:
            # Deletion is a change, too. A non-local reference has no current tree value.
            current = None
        if current != prior:
            missing.append(('changed', name))
    return missing
