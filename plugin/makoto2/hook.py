"""Locked append-only hook journal and fail-closed admission transport."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
from .observed import dependent
from .provenance import Ledger
from .evaluate import evaluate
from .transcript import history


FOUR_QUESTIONS = "Before this step: (1) If it relies on a definition, did you read the thing itself against that definition? (2) If it carries a result to another place or time, did you read the same thing again where and when it lands? (3) If it says how a branch behaves, did you feed that branch an input and read its response? (4) Is it based on the original source, read this turn, rather than on an earlier answer?"


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
    invocation = meta.get('invocation', {})
    if 'subject' in invocation and (not isinstance(invocation['subject'], str) or not invocation['subject']):
        raise ValueError('makoto.invocation.subject must be a nonempty string')
    if 'subjects' in invocation and (not isinstance(invocation['subjects'], list) or any(not isinstance(s, str) or not s for s in invocation['subjects'])):
        raise ValueError('makoto.invocation.subjects must contain nonempty strings')
    if 'prompt' in event and not isinstance(event['prompt'], str):
        raise ValueError('prompt must be text')
    for key in ('external_subjects', 'network_subjects'):
        if key in meta and (not isinstance(meta[key], list) or any(not isinstance(v, str) or not v for v in meta[key])):
            raise ValueError(key + ' must contain nonempty strings')
    if 'last_assistant_message' in event and not isinstance(event['last_assistant_message'], str):
        raise ValueError('last_assistant_message must be text')
    if event['hook_event_name'] in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure') and (not isinstance(event.get('tool_use_id'), str) or not event['tool_use_id']):
        raise ValueError('tool events require an exact tool_use_id')
    return event


REPORT_LIMIT = 700


def brief(report):
    """Report-only text is advice, not a gate: show the head, keep the count.

    The journal holds every finding; a 20 KB message per write costs the
    session more than the findings tell it.
    """
    if len(report) <= REPORT_LIMIT:
        return report
    return report[:REPORT_LIMIT].rstrip() + ' ... (%d more characters; the full findings are in the journal)' % (len(report) - REPORT_LIMIT)


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


def questions(event):
    if not dependent(event):
        return {}
    if event['hook_event_name'] == 'PreToolUse':
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'additionalContext': FOUR_QUESTIONS}}
    if not event.get('stop_hook_active'):
        return {'decision': 'block', 'reason': FOUR_QUESTIONS}
    return {}


def in_scope(cwd, prefixes):
    cwd = cwd.replace('\\', '/').rstrip('/').lower()
    for prefix in prefixes:
        prefix = prefix.replace('\\', '/').rstrip('/').lower()
        if prefix and (cwd == prefix or cwd.startswith(prefix + '/')):
            return True
    return False


def main(raw, config):
    event = {}
    try:
        envelope = json.loads(raw)
        if isinstance(envelope, dict):
            event = envelope  # Preserve boundary type for fail-closed transport.
        event = d_in(raw)
        adapter = config.get('adapter', 'inferred')
        if adapter != 'inferred':
            raise ValueError('adapter must be inferred')
        path = sigma_path(config['state_dir'], event['session_id'])
        with session_lock(path):
            journal = sigma_read(path, event['session_id'])
            # D20: a record that cannot be ingested is unknown, never partial evidence,
            # and never wedges later calls. Replay again without it; rare, so no per-record copy.
            records, skipped = list(history(event, journal)), {}
            while True:
                ledger = Ledger()
                for index, (prior, admitted) in enumerate(records):
                    if index in skipped:
                        ledger.q += 1
                        ledger.unknown.append({'q': ledger.q, 'reason': 'historical ingest failed: ' + skipped[index]})
                        continue
                    try:
                        ledger.ingest(prior, admitted)
                    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
                        skipped[index] = str(error)
                        break
                else:
                    break
            # Turn metadata on the candidate belongs to this check; its receipts do not.
            if event.get('makoto', {}).get('turn_id') is not None:
                ledger.turn = str(event['makoto']['turn_id'])
            findings, snapshot, contract = [], [], None
            if dependent(event):
                try:
                    findings, snapshot = evaluate(ledger, event, adapter)
                except (KeyError, TypeError, ValueError) as error:
                    contract = str(error)
            reason = None
            if contract:
                reason = 'makoto contract: ' + contract
            elif findings:
                reason = '; '.join('makoto rule ' + f['rule'] + ' [' + f['shape'] + ']: ' + json.dumps(f['subject'], ensure_ascii=False) + ': ' + f['missing'] for f in findings)
            report = None
            scope = config.get('block_in')
            if reason and scope and not in_scope(event.get('cwd') or '', scope):
                # Report only outside the listed projects: the step runs, the
                # journal keeps the finding, and nothing blocks.
                report, reason = reason, None
            row = {'event': event, 'admitted': not bool(reason), 'adapter': adapter,
                   'findings': findings, 'contract_error': contract, 'snapshot': snapshot,
                   'turn_id': ledger.turn, 'stop_hook_active_unpaid': bool(reason and event.get('stop_hook_active')),
                   'unknown': ledger.unknown}
            # Validate transitions before persisting invalid host records.
            ledger.ingest(event, row['admitted'])
            sigma_append(path, row, journal[-1]['sha256'] if journal else '')
            # Active Stop retries still block. Audit records mark the unpaid
            # retry; no suppression can silently admit its final text.
            if report:
                return {'systemMessage': 'makoto report only (outside block_in): ' + brief(report)}
            response = d_out(event, reason) if reason else questions(event)
            return response
    except (OSError, ValueError, KeyError, TypeError, RecursionError, AttributeError, IndexError) as error:
        if event.get('hook_event_name') in ('Stop', 'SubagentStop') and event.get('stop_hook_active'):
            return {'systemMessage': 'makoto transport/contract failure (not held twice): ' + str(error)}
        return d_out(event, 'makoto transport/contract failure: ' + str(error))
