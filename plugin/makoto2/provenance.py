"""One session ledger reconstructed from durable, ordered receipts."""
from .observed import identity, digest, native_reads, effects, completed, failed, response_text, text_of, values, WRITERS, FINAL


class Ledger:
    def __init__(self):
        self.q = 0
        self.turn = '0'
        self.pending = {}
        self.seen = set()
        self.readings = []
        self.definitions = []
        self.epochs = {}
        self.reservations = {}
        self.written = set()
        self.aliases = {}
        self.mutations = {}
        self.unknown = []
        self.relay_values = []
        self.commands = []
        self.scripts = {}

    def subject(self, value, event):
        result = identity(value, event)
        return self.aliases.get(result, result)

    def place(self, event):
        return event.get('makoto', {}).get('place', {'workspace': event.get('cwd', '')})

    def epoch_key(self, subject, place):
        return subject + '@' + digest(place)

    def advance(self, event):
        self.q += 1
        meta = event.get('makoto', {})
        if meta.get('turn_id') is not None:
            self.turn = str(meta['turn_id'])
        elif event['hook_event_name'] == 'UserPromptSubmit':
            self.turn = str(self.q)

    def ingest(self, event, admitted=True):
        self.advance(event)
        meta = event.get('makoto', {})
        name = event['hook_event_name']
        for alias in meta.get('aliases', []):
            self.aliases[identity(alias['alias'], event)] = self.subject(alias['subject'], event)
        # Host definitions on nondependent registration events only.
        if name in ('UserPromptSubmit', 'Register'):
            for definition in meta.get('definitions', []):
                item = dict(definition, subject=self.subject(definition['subject'], event), q=self.q)
                same = [d for d in self.definitions if (d['id'], d.get('revision')) == (item['id'], item.get('revision'))]
                if same and any(d != dict(item, q=d['q']) for d in same):
                    raise ValueError('definition revision is immutable')
                if not same:
                    self.definitions.append(item)
        if name in FINAL and admitted:
            self.relay_values.append({'subject': 'id:assistant:' + str(self.q), 'values': values(text_of(event))})
        if name == 'PreToolUse':
            tid = event.get('tool_use_id')
            if not admitted or not tid or tid in self.seen or tid in self.pending:
                return
            self.pending[tid] = (event, self.q, self.turn)
            reserved = {}
            for effect in effects(event):
                subject = self.subject(effect['subject'], event)
                reserved[subject] = meta.get('destination', self.place(event))
            self.reservations[tid] = reserved
        elif name in ('PostToolUse', 'PostToolUseFailure'):
            tid = event.get('tool_use_id')
            if tid not in self.pending or tid in self.seen:
                self.unknown.append({'q': self.q, 'reason': 'unpaired or replayed response'})
                return
            pre, pq, turn = self.pending[tid]
            # An ID is not enough if supplied tool identity/input disagree.
            if event.get('tool_name', pre.get('tool_name')) != pre.get('tool_name') or ('tool_input' in event and event['tool_input'] != pre.get('tool_input', {})):
                self.unknown.append({'q': self.q, 'reason': 'mismatched response'})
                return
            del self.pending[tid]
            self.seen.add(tid)
            reserved = self.reservations.get(tid, {})
            no_effect = meta.get('no_effect') is True
            if reserved and not no_effect and pre.get('tool_name') in WRITERS:
                ti = pre.get('tool_input', {})
                target = ti.get('file_path') or ti.get('notebook_path')
                if target:
                    # Only replacement bytes belong to the native writer target.
                    # Shell arguments and unrelated host effects carry no such link.
                    replacement = {k: v for k, v in ti.items() if k in
                                   ('content', 'new_string', 'new_source', 'cells')}
                    if isinstance(ti.get('edits'), list):
                        replacement['edits'] = [{'new_string': e['new_string']} for e in ti['edits']
                                                if isinstance(e, dict) and 'new_string' in e]
                    self.relay_values.append({'subject': self.subject(target, pre),
                                              'values': values(text_of(dict(pre, tool_input=replacement)))})
            if not no_effect:
                for subject in set(reserved) | {self.subject(x['subject'], pre) for x in effects(event)}:
                    place = reserved.get(subject, meta.get('destination', self.place(event)))
                    key = self.epoch_key(subject, place)
                    self.epochs[key] = self.epochs.get(key, 0) + 1
                    self.written.add(subject)
                    self.mutations[subject] = {'q': self.q, 'place': place}
                    content = text_of(pre)
                    target = pre.get('tool_input', {}).get('file_path') or pre.get('tool_input', {}).get('notebook_path')
                    if pre.get('tool_name') in WRITERS and target and subject == self.subject(target, pre) and (subject in self.scripts or subject.endswith(('.py', '.sh', '.js', '.rb', '.pl')) or content.startswith('#!') or pre.get('makoto', {}).get('executable') is True):
                        self.scripts[subject] = self.q
            # Failure alone cannot clear a potentially effective mutation.
            if not failed(event) or no_effect:
                self.reservations.pop(tid, None)
            if not completed(dict(event, tool_name=pre.get('tool_name'))):
                self.unknown.append({'q': self.q, 'reason': 'response not completed'})
                return
            if pre.get('tool_name') == 'Bash':
                from .surface import executable_inputs
                response = event.get('tool_response', {})
                self.commands.append({'command': pre.get('tool_input', {}).get('command', ''),
                    'inputs': pre.get('tool_input', {}), 'invocation': pre.get('makoto', {}).get('invocation', {}),
                    'exit_status': next((response[k] for k in ('exitCode', 'exit_code', 'exit') if k in response), None),
                    'turn': turn, 'pre_sequence': pq, 'sequence': self.q, 'executables': [self.subject(s, pre) for s in executable_inputs(pre)]})
            specs = native_reads(pre, event)
            wrapped = meta.get('reads', [])
            overridden = {(self.subject(x['subject'], pre), x.get('selector', 'content')) for x in wrapped}
            specs = [x for x in specs if (self.subject(x['subject'], pre), x.get('selector', 'content')) not in overridden] + wrapped
            if pre.get('tool_name') in WRITERS or reserved:
                specs = []  # Writes never create source receipts, even with read metadata.
            text = response_text(event.get('tool_response'))
            if pre.get('tool_name') in ('Agent', 'Task') and not wrapped:
                specs.append({'subject': 'id:relay:' + tid, 'complete': True, 'role': 'relay', 'producer': tid})
            if pre.get('tool_name') == 'Bash' and not native_reads(pre, event) and not pre.get('makoto', {}).get('invocation') and not reserved:
                self.unknown.append({'q': self.q, 'reason': 'general Bash subject/effects need host instrumentation'})
            # Every completed Bash invocation has an exact native command response.
            if pre.get('tool_name') == 'Bash':
                specs.append({'subject': 'command:' + digest([pre.get('cwd'), pre.get('tool_input', {}).get('command'), pre.get('makoto', {}).get('place', {})]),
                              'selector': 'response', 'complete': True, 'role': 'response'})
            for index, spec in enumerate(specs):
                subject = self.subject(spec['subject'], pre)
                invocation = pre.get('makoto', {}).get('invocation', {})
                self.readings.append(dict(spec, subject=subject, selector=spec.get('selector', 'content'),
                    tool=pre.get('tool_name'), receipt_id=f'{tid}:{index}', tool_use_id=tid, q=self.q, pre_q=pq, turn=turn,
                    point=dict(self.place(event), turn_id=turn, sequence=self.q, **({'timestamp': event['timestamp']} if 'timestamp' in event else {})),
                    epoch=self.epochs.get(self.epoch_key(subject, self.place(event)), 0), place=self.place(event), version=spec.get('version'),
                    complete=spec.get('complete') is True, value_sha256=spec.get('value_sha256', digest(text)),
                    values=sorted(values(text)), role=spec.get('role', 'relay' if subject in self.written else 'source'),
                    producer=spec.get('producer'), input_sha256=invocation.get('input_sha256'),
                    invocation_subject=self.subject(invocation['subject'], pre) if invocation.get('subject') else None,
                    invocation_selector=invocation.get('selector'), command=pre.get('tool_input', {}).get('command'),
                    command_context=[pre.get('cwd'), pre.get('makoto', {}).get('place', {})]))

    def available(self, reading, obligation, event, historical=False):
        if reading['q'] >= self.q + 1 or not reading['complete']:
            return False
        if reading['subject'] != self.subject(obligation['subject'], event) or reading['selector'] != obligation.get('selector', 'content'):
            return False
        if obligation.get('version') is not None and reading.get('version') != obligation['version']:
            return False
        if obligation.get('point') and not point_matches(reading['point'], obligation['point']):
            return False
        if not historical:
            if reading['epoch'] != self.epochs.get(self.epoch_key(reading['subject'], reading['place']), 0):
                return False
            if any(subjects.get(reading['subject']) == reading['place'] for subjects in self.reservations.values()):
                return False
        return True

    def matching(self, obligation, event, historical=False):
        return [r for r in self.readings if self.available(r, obligation, event, historical)]


def point_matches(actual, required):
    return isinstance(required, dict) and all(actual.get(k) == v for k, v in required.items())
