"""Deterministic token -> observation -> source/version ledger.

Only settled record bytes participate. A token match is evidence of possible
origin, never proof that an arbitrary prose conclusion follows from that source.
"""
import re
import os
from collections import defaultdict
from dataclasses import dataclass

_TOKEN = re.compile(r'(?<!\w)(?:\d{1,2}:\d{2}(?::\d{2})?|\d+(?:\.\d+)?%?|[\w]+(?:[-_][\w]+)*)(?!\w)')
_CHANGE = re.compile(r'\b(?:changed|updated|replaced|removed|recreated|cleared|unavailable)\b', re.I)
_GRAMMAR = frozenset('the a an is are was were has have current now old prior previous source reading value maximum minimum of for to from in at as by this that it its and or with after before'.split())
_UNVERIFIED = re.compile(r'\b(?:unverified|unknown|not evaluable|not-evaluable)\b', re.I)


def tokens(text):
    return frozenset(m.group().lower() for m in _TOKEN.finditer(str(text)))


@dataclass(frozen=True)
class Reading:
    seq: int
    source: str
    text: str
    values: frozenset
    original: bool
    dependencies: frozenset


class Trace:
    def __init__(self, record, reader):
        self.readings = []
        self.by_token = defaultdict(list)
        self.load_bearing = {'pass', 'passed', 'fail', 'failed', 'true', 'false'}
        self.latest = {}
        self.invalidated = {}
        self.reader = reader
        for obs in record.obs:
            if obs.failed:
                continue
            cwd = getattr(record, 'reader_evidence', {}).get(obs.seq, {}).get('cwd', '')
            if obs.tool in ('Write', 'Edit', 'MultiEdit'):
                for path in obs.written:
                    self.invalidated[path] = obs.seq
                continue
            identities = set(getattr(record, 'reader_evidence', {}).get(obs.seq, {}).get('source_reads', ()))
            if obs.tool == 'Read':
                identities.add(reader._norm(obs.input.get('file_path', ''), cwd))
            elif obs.tool == 'WebFetch':
                identities.add(obs.input.get('url', ''))
            elif obs.tool == 'Bash':
                segments = list(reader._segments(obs.input.get('command', '')))
                if len(segments) == 1 and segments[0][0] and segments[0][0][0] == 'cat':
                    identities.update(reader._norm(p, cwd) for p in segments[0][0][1:] if not p.startswith('-'))
                else:
                    identities.add('command:' + cwd + ':' + obs.input.get('command', ''))
            original = bool(identities) and obs.tool not in ('Agent', 'Task')
            if obs.tool == 'Read' and any(re.search(r'(?i)\b(?:answer|memo|receipt|digest|sweep|audit|summary)\b', os.path.basename(p).replace('-', ' ')) for p in identities):
                original = False
            if not identities:
                identities.add('relay:' + str(obs.seq))
            # Explicit citations inside a reading create edges to original sources.
            dependencies = set()
            for m in re.finditer(r'(?i)\bsource(?:\s+claimed)?\s*:\s*([^\n;]+)', obs.output):
                dependencies.update(reader._text_objects(m.group(1).rstrip('.'), cwd))
            for identity in identities - {''}:
                reading = Reading(obs.seq, identity, obs.output, tokens(obs.output), original, frozenset(dependencies))
                self.readings.append(reading)
                self.latest[identity] = reading
                for value in re.findall(r'(?:[:=]\s*[\"“]?)([\w-]+)', reading.text):
                    self.load_bearing.update(tokens(value))
                for match in re.finditer(r'[\"“]([^\"”]+)[\"”]', reading.text):
                    if not reading.text[match.end():].lstrip().startswith(':'):
                        self.load_bearing.update(tokens(match.group(1)))
                for token in reading.values:
                    self.by_token[token].append(reading)
            # A command that reports a changed subject invalidates previous
            # readings carrying the same measurement label and a changed value.
            if _CHANGE.search(obs.output):
                labels = tokens(re.sub(r'\b\d+(?:\.\d+)?\b', '', obs.output))
                for prior in self.readings:
                    if prior.seq >= obs.seq:
                        continue
                    if prior.source.startswith('command:'):
                        command = prior.source.split(':')[-1]
                        current = obs.input.get('command', '')
                        before_segments = list(reader._segments(command))
                        after_segments = list(reader._segments(current))
                        same_program = (len(before_segments) == len(after_segments) == 1
                                        and before_segments[0][0][:1] == after_segments[0][0][:1]
                                        and before_segments[0][0][0] not in ('cat', 'grep', 'rg', 'sed', 'head', 'tail', 'nl', 'cd'))
                        shared = (prior.values & labels) - {'the', 'is', 'a', 'current'}
                        if same_program and shared:
                            self.invalidated[prior.source] = obs.seq

    def current(self, reading):
        return (self.latest.get(reading.source) == reading
                and self.invalidated.get(reading.source, -1) < reading.seq)

    def origins(self, token):
        return tuple(self.by_token.get(token.lower(), ()))

    def stale(self, text):
        out = []
        for token in sorted(tokens(text)):
            # Load-bearing exact values: numbers/hashes and explicitly quoted
            # names. Ordinary connective words cannot establish a contradiction.
            if not (re.search(r'\d', token) or token in self.load_bearing):
                continue
            origins = self.origins(token)
            subject = tokens(text) - _GRAMMAR - {t for t in tokens(text) if re.search(r'\d', t)}
            related = tuple(r for r in origins if subject & r.values)
            if related:
                origins = related
            if origins and any(not self.current(r) for r in origins) and not any(self.current(r) and r.original for r in origins):
                out.append(token)
        return out

    def relay_sources(self, text):
        out = []
        if not re.search(r'(?i)\b(?:according to|based on|from|by)\b', text):
            return out
        for reading in self.readings:
            for source in reading.dependencies:
                if source not in self.latest:
                    out.append(source)
        if re.search(r'(?i)\b(?:prior answer|previous sweep|old audit)\b', text):
            claimed = tokens(text) & {'safe', 'compliant', 'automatically', 'allowed', 'permitted'}
            for reading in self.readings:
                if not reading.original and claimed & reading.values and not any(
                        r.original and r.seq > reading.seq and (claimed & r.values or tokens(text) & r.values - {'the', 'is', 'a', 'under', 'current'})
                        for r in self.readings):
                    out.append(reading.source)
        return sorted(set(out))

    def replaced_receipt(self, text):
        out = []
        claim_values = tokens(text)
        for reading in self.readings:
            if reading.original or reading.source.startswith(('command:', 'relay:')):
                continue
            if not re.search(r'(?i)\b(?:verified|passed|digest|receipt|snapshot)\b', reading.text):
                continue
            # A receipt followed by explicit loss of its verification subject.
            for later in self.readings:
                if later.seq <= reading.seq or not later.source.startswith('command:'):
                    continue
                if not _CHANGE.search(later.text):
                    continue
                if not ((tokens(text) - _GRAMMAR - {'verified', 'verification', 'passed', 'snapshot'}) & later.values):
                    continue
                if not re.search(r'(?i)\b(?:old|yesterday|snapshot|build|verification)\b', later.text):
                    continue
                carried = (reading.values & claim_values) - {'the', 'is', 'a', 'current', 'at', 'against'}
                if not any(re.search(r'\d', t) or t in ('passed', 'verified') for t in carried):
                    continue
                if any(r.seq > later.seq and r.original and r.source.startswith('command:')
                       and ((carried <= r.values) or
                            (re.search(r'(?i)verification complete|verified|passed', r.text)
                             and {t for t in claim_values if re.search(r'\d', t)} <= r.values))
                       for r in self.readings):
                    continue
                out.append(reading.source)
        return sorted(set(out))


def trace_for(record, reader):
    """Reuse one ledger across all checks of this immutable record snapshot."""
    cached = getattr(record, '_provenance_trace', None)
    if cached is None or cached.reader is not reader:
        cached = Trace(record, reader)
        record._provenance_trace = cached
    return cached


def violations(record, event, reader):
    from makoto2.family_lineage import output_text
    text = output_text(event, reader)
    if (not text
            or (event.get('tool_name') in ('Write', 'Edit')
                and str((event.get('tool_input') or {}).get('file_path', '')).endswith('.py'))):
        return []
    trace = trace_for(record, reader)
    out = []
    from makoto2.claim_reader import read_claims
    for claim in read_claims(record, event):
        if claim.get('kind') in ('question', 'cannot', 'plan', 'retracted'):
            continue
        sentence = claim.get('text', '')
        if not sentence:
            continue
        if claim.get('kind') == 'running' and not re.search(r'\b(?:is|are|was|were|currently)\s+running\b', sentence, re.I):
            continue
        if _UNVERIFIED.search(sentence) or re.search(r'(?i)\bnot current evidence\b', sentence):
            continue
        historical = (re.search(r'(?i)\b(?:old|previous|yesterday|earlier)\b', sentence)
                      and not re.search(r'(?i)\b(?:current|now|still|remain)\b', sentence))
        if not historical:
            out.extend(trace.stale(sentence))
        out.extend(trace.relay_sources(sentence))
        out.extend(trace.replaced_receipt(sentence))
    return sorted(set(out))
