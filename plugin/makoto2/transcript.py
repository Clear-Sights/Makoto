"""Read host transcript history without promoting assistant text to evidence.

Native JSONL hook rows and Claude message/tool_use/tool_result rows are accepted.
The current candidate is excluded. Journal decisions override matching imports.
"""
import json
from pathlib import Path
from .observed import digest


def key(event):
    name = event['hook_event_name']
    if name in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure'):
        return (name.replace('PostToolUseFailure', 'PostToolUse'), event.get('tool_use_id'))
    if name == 'UserPromptSubmit':
        return (name, digest(event.get('prompt', '')))
    return (name, digest(event))


def history(candidate, journal):
    path = candidate.get('transcript_path')
    if not path:
        return [(row['event'], row['admitted']) for row in journal]
    imported, pending = [], {}
    current_id = candidate.get('tool_use_id')
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row.get('session_id', row.get('sessionId', candidate['session_id'])) != candidate['session_id']:
                raise ValueError('transcript session identity mismatch')
            base = {'session_id': candidate['session_id'], 'cwd': row.get('cwd', candidate.get('cwd', ''))}
            if row.get('hook_event_name'):
                if row.get('tool_use_id') == current_id and row.get('hook_event_name') == 'PreToolUse':
                    break
                imported.append(dict(base, **row))
                continue
            message = row.get('message', {})
            role = message.get('role', row.get('type'))
            content = message.get('content', [])
            if role == 'user' and isinstance(content, str):
                imported.append(dict(base, hook_event_name='UserPromptSubmit', prompt=content))
            elif isinstance(content, list):
                prompts = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if role == 'assistant' and block.get('type') == 'tool_use':
                        if block['id'] == current_id:
                            return merge(imported, journal)
                        event = dict(base, hook_event_name='PreToolUse', tool_name=block['name'], tool_use_id=block['id'], tool_input=block.get('input', {}))
                        imported.append(event)
                        pending[block['id']] = event
                    elif role == 'user' and block.get('type') == 'tool_result':
                        tid = block['tool_use_id']
                        pre = pending.get(tid, {})
                        response = block.get('content', '')
                        if pre.get('tool_name') == 'Bash' and isinstance(response, str):
                            # No inferred exit status: host block status is authoritative.
                            response = {'stdout': response, 'is_error': block.get('is_error', False)}
                        elif block.get('is_error'):
                            response = {'content': response, 'is_error': True}
                        imported.append(dict(base, hook_event_name='PostToolUse', tool_name=pre.get('tool_name'), tool_use_id=tid, tool_input=pre.get('tool_input', {}), tool_response=response))
                    elif role == 'user' and block.get('type') == 'text':
                        prompts.append(block.get('text', ''))
                if prompts:
                    imported.append(dict(base, hook_event_name='UserPromptSubmit', prompt='\n'.join(prompts)))
    return merge(imported, journal)


def merge(imported, journal):
    """Anchor imported history to journal order, preserving denied decisions."""
    rows = [(r['event'], r['admitted']) for r in journal]
    def occurrence_keys(events):
        counts = {}
        for event in events:
            k = key(event)
            counts[k] = counts.get(k, 0) + 1
            yield (k, counts[k])
    positions = {k: i for i, k in enumerate(occurrence_keys(e for e, _ in rows))}
    result, cursor, used = [], 0, set()
    for event, k in zip(imported, occurrence_keys(imported)):
        if k in positions:
            at = positions[k]
            if at >= cursor:
                result.extend(rows[cursor:at+1])
                cursor = at + 1
            used.add(k)
        elif k not in used:
            result.append((event, True))
            used.add(k)
    result.extend(rows[cursor:])
    return result
