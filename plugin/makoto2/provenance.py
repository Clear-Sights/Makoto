"""Agnostic ordered sweep: source bytes, own output, writes, and online calls."""
import os
import re
from .borrowed import get, leaves, fragments
from .observed import (WRITERS, FINAL, identity, effects, failed,
                       reading_subjects, network_targets, response_text)
from .precision import contains, VERSIONED, package_parts


class Ledger:
    def __init__(self):
        self.q = 0
        self.turn = '0'
        self.pending = {}
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

    def subject(self, value, event):
        return identity(value, event)

    def fresh(self, item):
        return all(self.mutations.get(s, 0) < item['q'] and not any(s in targets for targets in self.reservations.values()) for s in item['subjects'])

    def source_readings(self):
        return [r for r in self.readings if r['source'] and self.fresh(r)]

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
                self.seen.add(tid)
        if pre is None or tid in self.seen or event.get('tool_name', pre.get('tool_name')) != pre.get('tool_name') or 'tool_input' in event and event['tool_input'] != pre.get('tool_input', {}):
            self.unknown.append({'q': self.q, 'reason': 'unpaired, replayed or mismatched tool result'})
            return
        del self.pending[tid]
        self.seen.add(tid)
        targets = self.reservations.get(tid, set()) | {self.subject(r['subject'], pre) for r in effects(event)}
        no_effect = meta.get('no_effect') is True
        if not no_effect:
            for subject in targets:
                self.mutations[subject] = self.q
                self.written.add(subject)
        if not failed(event) or no_effect:
            self.reservations.pop(tid, None)
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
        if not source:
            self.own.extend(texts)
            self.own.extend(v for _, v in leaves(pre.get('tool_input', {})))
        if source and not failed(event):
            network = network_targets(pre, event)
            if network and content_present:
                self.online.append(dict(item, texts=network + texts))
