"""Locked append-only hook journal and fail-closed admission transport."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
from .observed import dependent, FINAL
from .provenance import Ledger
from .evaluate import evaluate
from .obligations import ContractError
from .surface import render


def d_in(raw):
    event = json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    if not isinstance(event, dict) or not isinstance(event.get('hook_event_name'), str) or not event['hook_event_name']:
        raise ValueError('missing hook event')
    if not isinstance(event.get('session_id'), str) or not event['session_id']:
        raise ValueError('missing session identity')
    if not isinstance(event.get('makoto', {}), dict) or not isinstance(event.get('tool_input', {}), dict):
        raise ValueError('makoto and tool_input must be objects')
    meta = event.get('makoto', {})
    for key in ('definitions', 'reads', 'effects', 'obligations', 'dependencies', 'aliases'):
        if key in meta and (not isinstance(meta[key], list) or any(not isinstance(item, dict) for item in meta[key])):
            raise ValueError('makoto.' + key + ' must be an object list')
    for key in ('place', 'destination', 'points', 'invocation'):
        if key in meta and not isinstance(meta[key], dict):
            raise ValueError('makoto.' + key + ' must be an object')
    if 'last_assistant_message' in event and not isinstance(event['last_assistant_message'], str):
        raise ValueError('last_assistant_message must be text')
    if event['hook_event_name'] in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure') and (not isinstance(event.get('tool_use_id'), str) or not event['tool_use_id']):
        raise ValueError('tool events require an exact tool_use_id')
    return event


def sigma_path(state_dir, session_id):
    return Path(state_dir) / (hashlib.sha256(session_id.encode()).hexdigest() + '.jsonl')


@contextlib.contextmanager
def session_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + '.lock', 'a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def sigma_read(path, session_id):
    if not path.exists():
        return []
    result = []
    previous = ''
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            seal = row.pop('sha256')
            if row.get('previous') != previous or seal != hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest():
                raise ValueError('corrupted journal chain')
            if row['event']['session_id'] != session_id:
                raise ValueError('session identity collision')
            row['sha256'] = seal
            previous = seal
            result.append(row)
    return result


def sigma_append(path, row, previous):
    row['previous'] = previous
    row['sha256'] = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def d_out(event, reason):
    if not reason:
        return {}
    if event.get('hook_event_name') == 'PreToolUse':
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': reason}}
    return {'decision': 'block', 'reason': reason}


def main(raw, config):
    event = {}
    try:
        event = d_in(raw)
        adapter = config.get('adapter', 'inferred')
        if adapter != 'inferred':
            raise ValueError('adapter must be inferred')
        path = sigma_path(config['state_dir'], event['session_id'])
        with session_lock(path):
            journal = sigma_read(path, event['session_id'])
            ledger = Ledger()
            for row in journal:
                ledger.ingest(row['event'], row['admitted'])
            # Turn metadata on the candidate belongs to this check; its receipts do not.
            if event.get('makoto', {}).get('turn_id') is not None:
                ledger.turn = str(event['makoto']['turn_id'])
            findings, snapshot, contract = [], [], None
            surface = render(ledger, event) if dependent(event) else ''
            if dependent(event):
                try:
                    findings, snapshot = evaluate(ledger, event, adapter)
                except (ContractError, KeyError, TypeError, ValueError) as error:
                    contract = str(error)
            reason = None
            if contract:
                reason = 'makoto contract: ' + contract
            elif findings:
                reason = '; '.join('makoto ' + f['family'].replace('_', ' ') + ': ' + f['subject'] + ': ' + f['missing'] for f in findings)
            row = {'event': event, 'admitted': not bool(reason), 'adapter': adapter,
                   'findings': findings, 'contract_error': contract, 'snapshot': snapshot,
                   'surface': surface, 'turn_id': ledger.turn, 'stop_hook_active_unpaid': bool(reason and event.get('stop_hook_active')),
                   'unknown': ledger.unknown}
            # Validate transitions before persisting invalid host records.
            ledger.ingest(event, row['admitted'])
            sigma_append(path, row, journal[-1]['sha256'] if journal else '')
            # Active Stop retries still block. Audit records mark the unpaid
            # retry; no suppression can silently admit its final text.
            response = d_out(event, reason)
            if surface and event['hook_event_name'] == 'PreToolUse':
                specific = response.setdefault('hookSpecificOutput', {'hookEventName': 'PreToolUse'})
                specific['additionalContext'] = surface
            elif surface and event['hook_event_name'] in FINAL and not event.get('stop_hook_active'):
                response = d_out(event, (reason + '\n' if reason else '') + surface)
            return response
    except (OSError, ValueError, KeyError, TypeError, RecursionError, AttributeError, IndexError) as error:
        return d_out(event, 'makoto transport/contract failure: ' + str(error))
