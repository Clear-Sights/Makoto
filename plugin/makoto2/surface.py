"""Bounded factual view of the shared ledger; no inferred obligations."""
import json
import os
import re
from .observed import text_of, values, effects, WRITERS
from .obligations import manifest
from .provenance import point_matches


def exact(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def named_subjects(ledger, event):
    text = text_of(event)
    subjects = {r['subject'] for r in ledger.readings} | set(ledger.mutations)
    subjects |= {ledger.subject(o['subject'], event) for o in manifest(event) if 'subject' in o}
    result = set()
    for subject in subjects:
        spellings = [subject]
        if subject.startswith('file:'):
            path = subject[5:]
            spellings += [path, os.path.relpath(path, event.get('cwd') or os.getcwd())]
        if any(re.search(r'(?<![\w/])' + re.escape(s) + r'(?![\w/])', text) for s in spellings):
            result.add(subject)
    for token in values(text):
        if token.startswith(('/', './', '../', 'https://', 'http://')):
            result.add(ledger.subject(token, event))
    return result


def fresh(ledger, subject):
    mutation = ledger.mutations.get(subject)
    return any(r['subject'] == subject and r['complete'] and r['selector'] == 'content' and
               (not mutation or r['q'] > mutation['q'] and point_matches(r['point'], mutation['place']))
               for r in ledger.readings)


def hard_obligations(ledger, event):
    """Only host contracts and exact recorded mutation/read order."""
    result = manifest(event)
    targets = {ledger.subject(e['subject'], event) for e in effects(event)} if event.get('tool_name') in WRITERS else set()
    subjects = named_subjects(ledger, event) | targets
    for subject in sorted(subjects):
        if subject in ledger.mutations and not fresh(ledger, subject):
            result.append({'shape': 'OTHER_POINT', 'recorded_freshness': True, 'subject': subject})
    return result


def render(ledger, event):
    lines = []
    def emit(group, label, items):
        # Four items per factual category; omitted entries are counted exactly.
        items = sorted(set(items))
        if items:
            suffix = f'; +{len(items) - 4} more' if len(items) > 4 else ''
            lines.append(group + ': ' + label + ': ' + '; '.join(items[:4]) + suffix)

    reads = [r for r in ledger.readings if r['complete']]
    current = [r for r in reads if r['turn'] == ledger.turn]
    emit('LINEAGE', 'read this turn', [exact({'subject': r['subject'], 'tool': r['tool'], 'point': r['point'], 'selector': r['selector'], 'origin': r['role']}) for r in current])
    named = named_subjects(ledger, event)
    trace = values(text_of(event))
    carriers = {r['subject'] for r in reads + ledger.relay_values if trace.intersection(r['values'])}
    involved = named | carriers
    emit('LINEAGE', 'named or value-bearing subjects not read this turn', [exact(s) for s in involved if not any(r['subject'] == s for r in current)])
    relay_only = trace - {v for r in reads if r['role'] != 'relay' and not r.get('producer') for v in r['values']}
    emit('LINEAGE', 'values recorded only in assistant/relay/session-written text', [exact({'subject': r['subject'], 'values': sorted(relay_only.intersection(r['values']))}) for r in ledger.relay_values + [r for r in reads if r['role'] == 'relay' or r.get('producer')] if relay_only.intersection(r['values'])])
    subjects = {r['subject'] for r in reads}
    emit('OTHER POINT', 'read only once', [exact(s) for s in subjects if sum(r['subject'] == s for r in reads) == 1])
    emit('OTHER POINT', 'last reading predates last recorded mutation', [exact({'subject': s, 'reading_sequence': max(r['q'] for r in reads if r['subject'] == s), 'mutation_sequence': m['q']}) for s, m in ledger.mutations.items() if s in subjects and max(r['q'] for r in reads if r['subject'] == s) < m['q']])
    points = [(s, m['place']) for s, m in ledger.mutations.items()]
    for o in manifest(event):
        if 'subject' in o:
            points += [(ledger.subject(o['subject'], event), p) for p in o.get('points', [])]
            if o.get('point'):
                points.append((ledger.subject(o['subject'], event), o['point']))
    emit('OTHER POINT', 'no reading at recorded point', [exact({'subject': s, 'point': p}) for s, p in points if not any(r['subject'] == s and point_matches(r['point'], p) for r in reads)])
    emit('SWITCH', 'commands this turn', [exact(c) for c in ledger.commands if c['turn'] == ledger.turn])
    emit('SWITCH', 'session scripts/executables without a run after edit', [exact({'subject': s, 'edit_sequence': q}) for s, q in ledger.scripts.items() if not any(c['pre_sequence'] > q and s in c['executables'] for c in ledger.commands)])
    emit('SPEC', 'held definitions and bound reading', [exact({'id': d['id'], 'revision': d.get('revision'), 'subject': d['subject'], 'definition': {k: v for k, v in d.items() if k != 'q'}, 'reading': next((r['receipt_id'] for r in reversed(reads) if r['subject'] == d['subject'] and r['selector'] == d.get('selector', 'content') and r['q'] > d['q'] and (d.get('version') is None or r.get('version') == d['version']) and (d.get('point') is None or point_matches(r['point'], d['point']))), None)}) for d in ledger.definitions])
    return '\n'.join(lines)


def executable_inputs(pre):
    """Exact direct executable and interpreter script arguments only."""
    from .observed import argv, identity
    words = argv(pre)
    if not words or any(c in pre.get('tool_input', {}).get('command', '') for c in '|;&<>`$\n'):
        return []
    targets = [words[0]]
    if os.path.basename(words[0]) in ('python', 'python3', 'bash', 'sh', 'node', 'ruby', 'perl') and len(words) > 1 and not words[1].startswith('-'):
        targets.append(words[1])
    return [identity(t, pre) for t in targets]
