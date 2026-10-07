"""Agnostic ordered sweep: source bytes, own output, writes, and online calls."""
import os
import re
from .borrowed import get, leaves, fragments
from .observed import (WRITERS, FINAL, identity, effects, failed,
                       reading_subjects, network_targets, response_text)
from .precision import contains, VERSIONED, package_parts
from .switch import edited_forms, execution_subjects, run_output, full_read_subjects, compiled_subjects
from .shell import selected_segments
from .points import read_locations, located


class Ledger:
    def __init__(self):
        self.q = 0
        self.turn = '0'
        self.pending = {}
        self.pending_order = {}
        self.denied = {}
        self.seen = set()
        self.given = []
        self.readings = []
        self.inputs = []
        self.written = set()
        self.tainted = set()
        self.mutations = {}
        self.reservations = {}
        self.online = []
        self.external = []
        self.own = []
        self.unknown = []
        self.code_changes = {}
        self.executions = []
        self.readbacks = []
        self.shebangs = set()
        self.compiled = {}
        self.point_readings = []
        self.definitions = []
        self.point_aliases = []

    def changed_code(self):
        result = dict(self.code_changes)
        for tid, pre in self.pending.items():
            for effect in effects(pre):
                if effect.get('removed'):
                    continue
                form = edited_forms(pre, effect['subject'])
                if form:
                    subject = form['subject']
                    prior = result.get(subject, {})
                    form['aliases'] |= prior.get('aliases', set())
                    form['data'] = form['data'] and subject not in self.shebangs and prior.get('data', True)
                    form['q'] = self.pending_order[tid]
                    if form['q'] > prior.get('q', 0):
                        result[subject] = form
        # Records never run. Keep their observed forms internally so a shebang
        # seen before a shell edit can still establish a script obligation.
        return {subject: form for subject, form in result.items()
                if not (form.get('record') and form.get('data'))}

    def change_code(self, event, subject):
        if any(effect.get('removed') and self.subject(effect['subject'], event) == subject for effect in effects(event)):
            self.code_changes.pop(subject, None)
            self.shebangs.discard(subject)
            return
        spelling = next((effect['subject'] for effect in effects(event)
                         if self.subject(effect['subject'], event) == subject), subject)
        form = edited_forms(event, spelling)
        if form or subject in self.code_changes:
            prior = self.code_changes.get(subject, {})
            form = form or dict(prior)
            form['aliases'] = form['aliases'] | prior.get('aliases', set())
            replacement = event.get('tool_input', {}).get('content')
            full_write = event.get('tool_name') == 'Write' and isinstance(replacement, str)
            if full_write:
                if re.search(r'(?m)^#!\s*\S+', replacement):
                    self.shebangs.add(subject)
                else:
                    self.shebangs.discard(subject)
            form['data'] = form['data'] and subject not in self.shebangs and (full_write or prior.get('data', True))
            form['q'] = self.q
            form['tool_use_id'] = event.get('tool_use_id')
            self.code_changes[subject] = form

    def run_witnesses(self, change):
        return [run for run in self.executions if run['started'] > change['q']
                and change['subject'] in run['subjects']
                and not any(change['subject'] in self.reservations.get(tid, set()) for tid in self.pending)]

    def readback_witnesses(self, change):
        if not change.get('data') or change['subject'] in self.shebangs:
            return []
        return [read for read in self.readbacks if read['started'] > change['q']
                and change['subject'] in read['subjects']
                and not any(change['subject'] in self.reservations.get(tid, set()) for tid in self.pending)]

    def subject(self, value, event):
        return identity(value, event)

    def fresh(self, item):
        return all(self.mutations.get(s, 0) < item['q'] and not any(s in targets for targets in self.reservations.values()) for s in item['subjects'])

    def source_readings(self):
        return [r for r in self.readings if r['source'] and self.fresh(r)]

    def bash_order(self, pre, post, started, no_effect):
        """Apply lexical acts inside one paired call at distinct positions.

        Original read existence is independent of subsequent file changes;
        aggregate bytes still use the ordinary freshness guard for rule b.
        """
        if pre.get('tool_name') != 'Bash':
            return False
        segments = selected_segments(pre.get('tool_input', {}).get('command', ''), post)
        if segments is None:
            return False
        tid = pre['tool_use_id']
        for index, command in enumerate(segments):
            position = self.q + (index + 1) / (len(segments) + 1)
            segment = dict(pre, tool_input=dict(pre.get('tool_input', {}), command=command))
            # Host observations describe the whole call, never every segment.
            segment.pop('makoto', None)
            subjects = {self.subject(s, pre) for s in reading_subjects(segment)}
            original = subjects - (self.written | self.tainted)
            original -= set().union(*(s for key, s in self.reservations.items() if key != tid))
            response = post.get('tool_response')
            if (len(segments) > 1 and original and bool(list(leaves(response)))
                    and not (isinstance(response, dict) and any(response.get(key)
                             for key in ('backgroundTaskId', 'session_id', 'sessionId', 'running')))
                    and not any(r.get('producer') or r.get('role') == 'relay'
                                for ev in (pre, post) for r in ev.get('makoto', {}).get('reads', []))):
                self.readings.append({'q': position, 'subjects': [], 'texts': [],
                                      'source': True, 'tool_use_id': tid, 'tool': 'Bash',
                                      'turn': self.turn, 'original_subjects': sorted(original)})
            if not no_effect:
                for effect in effects(segment):
                    subject = self.subject(effect['subject'], pre)
                    self.mutations[subject] = position
                    self.written.add(subject)
                    self.compiled.pop(subject, None)
                    self.change_code(segment, subject)
                    if subject in self.code_changes:
                        self.code_changes[subject]['q'] = position
            if run_output(post):
                compiled = compiled_subjects(segment)
                if compiled and not failed(post):
                    product, sources = compiled
                    self.compiled[product] = {'subjects': sources, 'q': position,
                                              'starts': {s: position if self.code_changes.get(s, {}).get('tool_use_id') == tid
                                                         else started for s in sources}}
                invoked = execution_subjects(segment, self.code_changes)
                if invoked:
                    for subject in invoked:
                        run_start = position if self.code_changes.get(subject, {}).get('tool_use_id') == tid else started
                        self.executions.append({'q': position, 'started': run_start,
                                                'subjects': {subject}, 'tool_use_id': tid})
                    for product in invoked:
                        build = self.compiled.get(product)
                        if build and build['q'] < position:
                            for subject in build['subjects']:
                                self.executions.append({'q': position, 'started': build['starts'][subject],
                                                        'subjects': {subject}, 'tool_use_id': tid})
            complete = full_read_subjects(segment, post)
            if complete:
                for subject in complete:
                    read_start = position if self.code_changes.get(subject, {}).get('tool_use_id') == tid else started
                    self.readbacks.append({'q': position, 'started': read_start,
                                           'subjects': {subject}, 'tool_use_id': tid})
        return True

    def witnesses(self, span, kind=None):
        if any(contains(text, span, kind) for text in self.given):
            return [{'given': True}]
        return [r for r in self.source_readings() + [i for i in self.inputs if self.fresh(i)] if any(contains(text, span, kind) for text in r['texts'])]

    def fetched(self, span, kind=None):
        parts = package_parts(span)
        return [r for r in self.online if r['turn'] == self.turn and self.fresh(r) and any(
            contains(t, span) or parts and any(package_parts(m.group()) == parts for m in VERSIONED.finditer(t))
            for t in r['texts'])]

    def ingest(self, event, admitted=True):
        self.q += 1
        name, meta = event['hook_event_name'], event.get('makoto', {})
        if admitted:
            self.definitions.extend(meta.get('definitions', []))
            self.point_aliases.extend(frozenset((located(a['subject'], event)[0], located(a['alias'], event)[0]))
                                      for a in meta.get('aliases', []))
        if meta.get('turn_id') is not None:
            self.turn = str(meta['turn_id'])
        elif name == 'UserPromptSubmit':
            self.turn = str(self.q)
        if name in ('UserPromptSubmit', 'Register'):
            self.external.extend(meta.get('external_subjects', []))
        if name in FINAL or name == 'AssistantMessage':
            self.own.extend(v for _, v in leaves(event.get('last_assistant_message', event.get('content', ''))))
        if name == 'UserPromptSubmit':
            self.given.append(event.get('prompt', ''))
        if name == 'PreToolUse':
            tid = event.get('tool_use_id')
            if not admitted:
                self.denied.setdefault(tid, event)
                return
            if tid in self.pending or tid in self.seen:
                return
            targets = {self.subject(r['subject'], event) for r in effects(event)}
            self.pending[tid] = event
            self.pending_order[tid] = self.q
            self.reservations[tid] = targets
            if event.get('tool_name') not in WRITERS and not targets and event.get('tool_name') not in ('Agent', 'Task'):
                self.inputs.append({'q': self.q, 'subjects': [self.subject(s, event) for s in reading_subjects(event)],
                                    'texts': list(fragments(event.get('tool_input', {}))), 'tool_use_id': tid})
            return
        if name not in ('PostToolUse', 'PostToolUseFailure'):
            return  # Assistant text, even a paid final, never supplies evidence.
        tid = event.get('tool_use_id')
        pre = self.pending.get(tid)
        if pre is None and tid in self.denied and tid not in self.seen:
            denied = self.denied[tid]
            if (event.get('tool_name', denied.get('tool_name')) == denied.get('tool_name')
                    and ('tool_input' not in event or event['tool_input'] == denied.get('tool_input', {}))
                    and meta.get('no_effect') is not True):
                # A host-reported completion after denial cannot pay evidence,
                # but its mutation must invalidate old reads and taint readbacks.
                for effect in effects(denied) + effects(event):
                    subject = self.subject(effect['subject'], denied)
                    self.mutations[subject] = self.q
                    self.tainted.add(subject)
                    self.change_code(denied, subject)
                self.seen.add(tid)
        if pre is None or tid in self.seen or event.get('tool_name', pre.get('tool_name')) != pre.get('tool_name') or 'tool_input' in event and event['tool_input'] != pre.get('tool_input', {}):
            self.unknown.append({'q': self.q, 'reason': 'unpaired, replayed or mismatched tool result'})
            return
        del self.pending[tid]
        started = self.pending_order.pop(tid)
        self.seen.add(tid)
        targets = self.reservations.get(tid, set()) | {self.subject(r['subject'], pre) for r in effects(event)}
        no_effect = meta.get('no_effect') is True
        ordered = self.bash_order(pre, event, started, no_effect)
        native = dict(pre)
        native.pop('makoto', None)
        native_targets = {self.subject(r['subject'], pre) for r in effects(native)} if ordered else set()
        if not no_effect:
            for subject in targets:
                if subject in native_targets:
                    continue
                self.mutations[subject] = self.q
                self.written.add(subject)
                self.change_code(pre, subject)
        if not failed(event) or no_effect:
            self.reservations.pop(tid, None)
        # Paired call plus returned response proves the act, even on failure.
        # Resolve the invocation against its recorded cwd, never final prose.
        if run_output(event) and (not ordered or pre.get('makoto', {}).get('invocation') or meta.get('invocation')):
            invoked = execution_subjects(pre, self.code_changes, event)
            if invoked:
                self.executions.append({'q': self.q, 'started': started,
                                        'subjects': invoked, 'tool_use_id': tid})
        complete = full_read_subjects(pre, event)
        if complete and pre.get('tool_name') not in WRITERS | {'Agent', 'Task'}:
            if not ordered or pre.get('makoto', {}).get('reads') or meta.get('reads'):
                self.readbacks.append({'q': self.q, 'started': started,
                                       'subjects': complete, 'tool_use_id': tid})
            shebang = bool(re.search(r'(?m)^#!\s*\S+', response_text(event.get('tool_response'))))
            for subject in complete:
                change = self.code_changes.get(subject)
                if change and started <= change['q']:
                    continue
                if shebang:
                    self.shebangs.add(subject)
                else:
                    self.shebangs.discard(subject)
                if change and change.get('data_form'):
                    change['data'] = not shebang
        response = event.get('tool_response')
        if response is None or isinstance(response, dict) and response.get('backgroundTaskId'):
            return
        subjects = [self.subject(s, pre) for s in reading_subjects(pre)]
        subjects += [self.subject(r['subject'], pre) for r in meta.get('reads', [])]
        texts = list(fragments(response))
        content_present = bool(list(leaves(response)))
        tool = pre.get('tool_name')
        # A completed run reads an external response, even if it also mutates
        # something. Direct readbacks of session-written files remain own output.
        source = tool not in WRITERS | {'Agent', 'Task'} and not any(s in self.written | self.tainted for s in subjects)
        for spec in meta.get('reads', []) + pre.get('makoto', {}).get('reads', []):
            if spec.get('role') == 'relay' or spec.get('producer'):
                source = False
        # Expand only references actually present in this response, never a store scan.
        if source:
            store = meta.get('detio_store') or pre.get('makoto', {}).get('detio_store') or os.environ.get('DETIO_STORE_DIR')
            for text in list(texts):
                refs = re.findall(r'detio://([0-9a-f]{64}|[0-9a-f]{12})(?![0-9a-f])', text)
                if store:
                    refs += re.findall(re.escape(str(os.path.expanduser(store)).rstrip('/') + '/objects/') + r'([0-9a-f]{64}|[0-9a-f]{12})(?![0-9a-f])', text)
                for address in refs:
                    if not store:
                        raise ValueError('DetIO reference needs a recorded store directory')
                    texts.append(get(store, address))
        item = {'q': self.q, 'subjects': subjects, 'texts': texts,
                'source': source, 'tool_use_id': tid, 'tool': tool, 'turn': self.turn}
        # Empty file content is a reading; empty writer acknowledgments are not.
        if content_present:
            self.readings.append(item)
        # A direct readback can establish the state of that file itself even
        # though its bytes cannot serve as an original source for rule a.
        relay = any(r.get('producer') or r.get('role') == 'relay'
                    for ev in (pre, event) for r in ev.get('makoto', {}).get('reads', []))
        ongoing = isinstance(response, dict) and any(response.get(k) for k in
                  ('backgroundTaskId', 'session_id', 'sessionId', 'running'))
        if content_present and not ongoing and not failed(event) and tool not in WRITERS | {'Agent', 'Task'} and not relay:
            acts = [(pre, started)]
            if tool == 'Bash':
                segments = selected_segments(pre.get('tool_input', {}).get('command', ''), event)
                acts = []
                for index, command in enumerate(segments or []):
                    position = self.q + (index + 1) / (len(segments) + 1)
                    acts.append((dict(pre, tool_input=dict(pre.get('tool_input', {}), command=command)), position))
            for act, position in acts:
                for path, point in read_locations(act):
                    # Only an ordered mutation inside this call can move the
                    # reading past its start; overlapping calls stay unpaid.
                    mutation = self.mutations.get(self.subject(path, pre), 0)
                    read_start = position if mutation > self.q else started
                    self.point_readings.append({'path': path, 'point': point,
                                                'started': read_start, 'tool_use_id': tid})
        if not source:
            self.own.extend(texts)
            self.own.extend(v for _, v in leaves(pre.get('tool_input', {})))
        if source and not failed(event):
            network = network_targets(pre, event)
            if network and content_present:
                self.online.append(dict(item, texts=network + texts))
