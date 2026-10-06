"""Two replaceable O(e) adapters. Obligations and receipt ownership are distinct."""
import re
from .observed import text_of, values, identity, digest


class ContractError(ValueError):
    pass


def manifest(event):
    meta = event.get('makoto', {})
    return list(meta.get('obligations', [])) + [dict(d, shape='LINEAGE') for d in meta.get('dependencies', [])]


def basis_text(event):
    ti = event.get('tool_input', {})
    description = ti.get('description', '')
    content = event.get('last_assistant_message', '') if event['hook_event_name'] in ('Stop', 'SubagentStop', 'PreDelivery') else '\n'.join(str(ti.get(k, '')) for k in ('content', 'new_string', 'new_source', 'command'))
    candidates = description.splitlines() + content.splitlines()[:1]
    for line in candidates:
        line = re.sub(r'^\s*(?:#|//|/\*|<!--)\s*', '', line).strip()
        if line.startswith('makoto-basis:'):
            return line[len('makoto-basis:'):].removesuffix('*/').removesuffix('-->').strip()
    return None


def parse_basis(line):
    fields = {}
    if not line:
        return fields
    for section in line.split(';'):
        if not section.strip():
            continue
        key, sep, value = section.strip().partition('=')
        if not sep or key not in ('source', 'second', 'act', 'def') or key in fields:
            raise ContractError('invalid basis field; use source, second, act, def once each')
        fields[key] = [x.strip() for x in value.split(',') if x.strip()]
    return fields


def declaration(event, ledger):
    line = basis_text(event)
    if line is None:
        raise ContractError('LINEAGE: add a makoto-basis line naming the readings this step uses (an empty line declares a novel output)')
    fields = parse_basis(line)
    obligations = manifest(event)
    for subject in fields.get('source', []):
        obligations.append({'shape': 'LINEAGE', 'subject': subject})
    for entry in fields.get('def', []):
        did, sep, subject = entry.partition(':')
        if not sep or not subject:
            raise ContractError('SPEC: use def=<definition id>:<subject>')
        definitions = [d for d in ledger.definitions if d['id'] == did and d['subject'] == ledger.subject(subject, event)]
        definition = definitions[-1] if definitions else {}
        obligations.append({'shape': 'SPEC', 'definition_id': did, 'subject': subject,
                            'selector': definition.get('selector', 'content'), 'definition_revision': definition.get('revision')})
    for entry in fields.get('second', []):
        subject, sep, point = entry.rpartition('@')
        if not sep or not point:
            raise ContractError('OTHER POINT: use second=<subject>@<point>')
        # Named points resolve from an operator/host point registry, otherwise
        # the exact revision string supplies the required destination point.
        target = event.get('makoto', {}).get('points', {}).get(point, {'revision': point})
        readings = ledger.matching({'subject': subject}, event, historical=True)
        first = readings[0]['point'] if readings else {'sequence': -1}
        obligations.append({'shape': 'OTHER_POINT', 'subject': subject, 'points': [first, target]})
    for entry in fields.get('act', []):
        command, sep, subject = entry.rpartition('->')
        if not sep or not command or not subject:
            raise ContractError('SWITCH: use act=<command>-><subject>')
        obligations.append({'shape': 'SWITCH', 'subject': subject, 'command': command, 'selector': 'content'})
    covered = {ledger.subject(o['subject'], event) for o in obligations if 'subject' in o}
    content = text_of(event)
    trace = values(content)
    # Exact values already known from this turn cannot be silently omitted.
    for reading in ledger.readings:
        if reading['turn'] == ledger.turn and reading['role'] == 'source' and trace.intersection(reading['values']) and reading['subject'] not in covered:
            raise ContractError('LINEAGE: understated basis; add source=' + reading['subject'] + ' for the value taken from that reading')
    return obligations


def inference(event, ledger):
    obligations = manifest(event)
    text = text_of(event)
    named = set()
    for reading in ledger.readings:
        subject = reading['subject']
        spelling = subject[5:] if subject.startswith('file:') else subject
        # Exact delimited identities only; relative aliases are parsed structurally.
        if spelling in values(text) or subject in values(text):
            named.add(subject)
    for token in values(text):
        if token.startswith(('/', './', '../', 'http://', 'https://')):
            candidate = ledger.subject(token, event)
            if any(r['subject'] == candidate for r in ledger.readings):
                named.add(candidate)
    for subject in named:
        obligations.append({'shape': 'LINEAGE', 'subject': subject})
        if subject in ledger.mutations:
            mutation = ledger.mutations[subject]
            previous = [r for r in ledger.readings if r['subject'] == subject and r['q'] < mutation['q']]
            first = previous[-1]['point'] if previous else {'sequence': -1}
            obligations.append({'shape': 'OTHER_POINT', 'subject': subject,
                                'points': [first, mutation['place']], 'after_sequence': mutation['q']})
    for token in values(text):
        origins = [r for r in ledger.readings if token in r['values']]
        if origins:
            # A traceable value has an exact eligible source, not just a relay.
            eligible = [r for r in origins if r['turn'] == ledger.turn and r['role'] == 'source' and not r.get('producer') and ledger.available(r, r, event)]
            if not eligible:
                obligations.append({'shape': 'LINEAGE', 'subject': origins[-1]['subject'], 'selector': origins[-1]['selector']})
    # SPEC and SWITCH are inferred only from exact host obligation records;
    # no numeric relation, adjective, or arbitrary successful Bash is inferred.
    return obligations


ADAPTERS = {'declared': declaration, 'inferred': inference}
