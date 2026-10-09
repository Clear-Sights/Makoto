"""Four pre-step holds derived only from literal session observations."""
import os
import re
from .precision import extract, names, contains, package_parts
from .observed import text_of, effects
from .borrowed import receipt
from .switch import names_change
from .paths import path_spellings
from .shipping import commit_changes, git_calls
from .creations import introduces


def evaluate(ledger, event, adapter='inferred'):
    if adapter != 'inferred':
        raise ValueError('adapter must be inferred')
    text = text_of(event)
    shipping = commit_changes(ledger, event) if event.get('tool_name') == 'Bash' else None
    if shipping is not None:
        # Git options, identity and path selection are operation syntax. Only
        # commit messages make authored claims; d checks the recorded revisions.
        messages = []
        for _, action, args in git_calls(event):
            if action != 'commit':
                continue
            for i, arg in enumerate(args):
                if arg in ('-m', '--message') or re.fullmatch(r'-[a-zA-Z]*m', arg):
                    if i + 1 < len(args):
                        messages.append(args[i + 1])
                elif arg.startswith('--message='):
                    messages.append(arg.split('=', 1)[1])
        text = '\n'.join(messages)
    creation = introduces(ledger, event)
    readings = ledger.source_readings()
    findings, snapshot = [], []
    spans = extract(text)
    name_spans = [] if creation else names(text)
    output_subjects = ledger.written | {ledger.subject(r['subject'], event) for r in effects(event)}
    output_ranges = []
    # Whitespace in an output filename can split lexical tokens. Exempt those
    # slices only within a complete output path, with exact token boundaries.
    for subject in output_subjects:
        if subject.startswith('file:') and ' ' in subject:
            absolute = subject[5:]
            for path in path_spellings(absolute, event.get('cwd') or os.getcwd()):
                pattern = r'(?<![\w/\\.@:+~%#?=&$!*|-])' + re.escape(path) + r'(?![\w/\\.@:+~%#?=&$!*|-])'
                output_ranges.extend(m.span() for m in re.finditer(pattern, text))

    # An id the write itself defines (first table cell, heading, list label) is
    # authored here, not a reference to something unread. Uses of other ids still hold.
    defined = set(re.findall(r'(?m)^\s*\|\s*\**([A-Za-z][\w.-]*)\**\s*\|', text))
    defined |= set(re.findall(r'(?m)^\s*(?:#+|[-*])\s+\**([A-Za-z][\w.-]*\d)\**(?=[\s:.)]|$)', text))

    # A new script binds its own functions, classes and variables; writing them
    # is authoring, not citing something unread. Only code files qualify.
    authored = set()
    target = (event.get('tool_input') or {}).get('file_path') or ''
    if event.get('tool_name') == 'Write' and re.search(r'\.(?:py|sh|bash|js|mjs|ts)$', target):
        defined |= set(re.findall(r'(?m)^[ \t]*(?:async\s+)?(?:def|class|function)\s+([A-Za-z_]\w*)', text))
        defined |= set(re.findall(r'(?m)^[ \t]*(?:(?:export\s+)?(?:const|let|var)\s+)?([A-Za-z_]\w*)\s*=(?!=)', text))
        defined |= set(re.findall(r'(?m)^[ \t]*for\s+([A-Za-z_]\w*)\s+in\b', text))
        # The interpreter line and the file's own name are authored here too.
        # Any other path in the text, even a constant, still needs a reading.
        shebang = re.search(r'(?m)^#!(\S+)(?:[ \t]+(\S+))?', (event.get('tool_input') or {}).get('content') or '')
        shebang = shebang if shebang and shebang.start() == 0 else None
        if shebang:
            authored |= {'#!' + shebang.group(1), *( [shebang.group(2)] if shebang.group(2) else [] )}
            defined |= set(filter(None, [shebang.group(2)]))
        authored.add(os.path.basename(target))

    def output_name(span):
        if span.kind == 'identifier' and span.text in defined:
            return True
        if span.kind == 'path' and (span.text in authored or span.text.rstrip('.') in authored):
            return True
        return span.kind == 'path' and ledger.subject(span.text, event) in output_subjects or any(start <= span.start and span.end <= end for start, end in output_ranges)

    if not readings and not creation and (shipping is None or name_spans):
        span = spans[0].text if spans else text
        findings.append({'rule': 'a', 'family': 'a', 'shape': 'lineage', 'subject': span,
                         'missing': 'ANSWER FROM ITS OWN ANSWER: read an original artifact before this step; assistant text and files this session wrote do not clear it'})
    # Rule a asks whether an original artifact was read. It does not require
    # a derived result or repeated answer to occur verbatim in that artifact.
    # Exact unread names remain governed independently by rule b.
    for span in name_spans:
        cited = span
        if span.kind == 'path' and re.search(r':\d+(?::\d+)?$', span.text):
            # `file.py:12` cites a line of the file: the file read, or the
            # exact citation seen in output, evidences it.
            base = re.sub(r':\d+(?::\d+)?$', '', span.text)
            span = type(span)(base, span.start, span.start + len(base), span.kind)
        if output_name(span):
            snapshot.append({'span': span.text, 'kind': span.kind, 'output': True})
            continue
        witnesses = ledger.witnesses(span.text, span.kind) or ledger.witnesses(cited.text, cited.kind)
        if (span.kind == 'path' and not span.text.startswith('#!')
                and any(contains(t, span.text, span.kind) for t in ledger.given)):
            # Naming a file in the prompt does not read its contents.
            witnesses = [w for w in witnesses if not w.get('given')]
            if not witnesses:
                witnesses = [r for r in ledger.source_readings() if any(contains(t, span.text, span.kind) for t in r['texts'])]
        if not witnesses:
            findings.append({'rule': 'b', 'family': 'b', 'shape': 'spec', 'subject': span.text,
                             'missing': 'NAMED WITHOUT READING: read a source whose tool input or response contains these exact characters; a different spelling or stale reading does not clear it'})
        else:
            snapshot.append({'span': span.text, 'kind': span.kind,
                             'reading_receipt_ids': [w.get('tool_use_id', 'user prompt') for w in witnesses]})
    # A URL built from shell variables is a template, and a shell's own version
    # floor is a local requirement: neither names an outside subject.
    external = [s.text for s in spans + name_spans
                if (s.kind == 'url' and not re.search(r'\$[\w{(]|\{\{|<[a-z_]+>', s.text))
                or s.kind == 'external-package' and re.search(r'@|==|>=|<=|~=|\bversion\s|\sv\d', s.text)
                and not re.match(r'(?:ba|z|da|k)?sh\b', s.text)]
    # An earlier online response can establish a package's external identity;
    # it still needs a fresh online receipt in the current turn.
    for span in spans:
        parts = package_parts(span.text) if span.kind == 'external-package' else None
        if parts and any(contains(t, span.text) for r in ledger.online for t in r['texts']):
            external.append(span.text)
    # Host-classified public projects are checked by the same literal sweep.
    external += [s for s in ledger.external + event.get('makoto', {}).get('external_subjects', []) if contains(text, s)]
    for span in dict.fromkeys(external):
        if not ledger.fetched(span):
            findings.append({'rule': 'c', 'family': 'c', 'shape': 'other point', 'subject': span,
                             'missing': 'DID NOT LOOK ONLINE: fetch or search this exact external subject with WebFetch, WebSearch or a Bash network call in this turn'})
    for change in (shipping if shipping is not None else ledger.changed_code()).values():
        if shipping is None and not names_change(event, change):
            continue
        runs = ledger.run_witnesses(change)
        readbacks = ledger.readback_witnesses(change)
        if not runs and not readbacks:
            findings.append({'rule': 'd', 'family': 'd', 'shape': 'switch',
                             'subject': change['display'],
                             'missing': 'UNRUN CHANGE: run it and read the output before this step'})
        else:
            witnesses = runs or readbacks
            snapshot.append(receipt(change['display'], [run['tool_use_id'] for run in witnesses],
                                    'makoto2.switch/execution-v1' if runs else 'makoto2.switch/readback-v1'))
    if not findings and readings:
        snapshot.append(receipt(text, [r['tool_use_id'] for r in readings], 'makoto2.precision/form-v1'))
    return list({(f['rule'], f['subject']): f for f in findings}.values()), snapshot
