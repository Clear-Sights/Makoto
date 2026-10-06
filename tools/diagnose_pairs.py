#!/usr/bin/env python3
"""Diagnose a matching checker-version grade without opening recorded subjects.

Run before changing the checker; --after preserves that baseline diagnosis and
compares a subsequent grade without reconstructing the baseline with new code.
"""
import argparse
import csv
import json
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin'))
from makoto2 import hook
from makoto2.provenance import Ledger
from makoto2.observed import text_of, network_targets
from makoto2.precision import extract, names


def rules(response):
    return set(re.findall(r'makoto rule ([abc]):', json.dumps(response)))


def explain(session, grade):
    ledger = Ledger()
    with tempfile.TemporaryDirectory() as state:
        config = {'state_dir': state, 'adapter': 'inferred'}
        findings = []
        for index, original in enumerate(session['events'][:session['step_index'] + 1]):
            event = dict(original, session_id='diagnostic', cwd=original.get('cwd') or '/record')
            response = hook.main(json.dumps(event), config)
            journal = hook.sigma_read(hook.sigma_path(state, 'diagnostic'), 'diagnostic')
            row = journal[-1]
            if index == session['step_index']:
                findings = row['findings']
                break
            ledger.ingest(event, row['admitted'])
    text = text_of(event)
    active = rules(grade['response'])
    expected = session['expect'] == 'hold'
    target = {'OWN-ANSWER': 'a', 'UNREAD-NAME': 'b', 'NOT-ONLINE': 'c'}[session['cause']]
    reasons = []
    if target == 'a' and (('a' in active) != expected):
        if expected:
            reasons.append('Denied writer result ignored as unpaired; subsequent own-file read becomes an original source: ' + json.dumps(ledger.unknown))
        elif ledger.source_readings():
            reasons.append('Original reading exists but literal-copy guard requires derived/repeated prose and precision values verbatim in source bytes: ' + json.dumps([f['subject'] for f in findings if f['rule'] == 'a']))
        else:
            reasons.append('No eligible original reading: ' + json.dumps(ledger.readings))
    external = [s.text for s in extract(text) + names(text) if s.kind in ('url', 'external-package')]
    if target == 'c' and expected and 'c' not in active:
        reasons.append('Bare public subject has no URL/version form or host external_subjects classification: ' + json.dumps(text))
    if not expected and 'c' in active:
        for span in dict.fromkeys(f['subject'] for f in findings if f['rule'] == 'c'):
            if span.endswith('.') and re.search(r'\d\.', span):
                reasons.append('VERSIONED captures sentence punctuation as part of external name: ' + json.dumps(span))
            network_calls = []
            for post in session['events'][:session['step_index']]:
                if post['hook_event_name'] == 'PostToolUse' and post.get('tool_name') == 'Bash':
                    network_calls.append({'input': post.get('tool_input'), 'response': post.get('tool_response'), 'recognized': network_targets(post, post)})
            if network_calls:
                reasons.append('Completed native Bash fetch with text response lacks explicit zero exit-status; discarded by online ledger: ' + json.dumps(network_calls))
            if target != 'c':
                reasons.append('Non-external local version is promoted by adjacent-word VERSIONED syntax, with no evidence of public-package authority: ' + json.dumps(span))
    if not reasons:
        reasons.append('Target rule differs from label; see exact unpaid-name findings and readings.' if (target in active) != expected else
                       'Target rule matches label; native held may also include another rule or the once-only four-question reminder.')
    return {'target_rule': target, 'target_held': target in active,
            'fired_rules': ''.join(sorted(active)), 'diagnosis': ' | '.join(reasons),
            'findings': json.dumps(findings, ensure_ascii=False),
            'readings': json.dumps(ledger.readings, ensure_ascii=False),
            'online': json.dumps(ledger.online, ensure_ascii=False),
            'external_forms': json.dumps(external, ensure_ascii=False)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pairs', type=Path)
    parser.add_argument('grade', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--after', type=Path, help='Append a later grade to the existing baseline diagnosis')
    options = parser.parse_args()
    data = json.loads(options.pairs.read_text())
    sessions = data if isinstance(data, list) else data['sessions']
    grades = [json.loads(line) for line in options.grade.read_text().splitlines()]
    if len(sessions) != len(grades):
        raise ValueError('grade must have one row per session')
    if options.after:
        after = [json.loads(line) for line in options.after.read_text().splitlines()]
        with (options.destination / 'DIAG.tsv').open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        if len(after) != len(rows):
            raise ValueError('later grade must have one row per session')
        for row, grade in zip(rows, after):
            active = rules(grade['response'])
            row['after_native_held'] = grade['held']
            row['after_target_held'] = row['target_rule'] in active
            row['after_rules'] = ''.join(sorted(active))
            row['residual'] = ('target miss' if row['expect'] == 'hold' else 'target false hold') if row['after_target_held'] != (row['expect'] == 'hold') else 'target matches'
            row['after_response'] = json.dumps(grade['response'], ensure_ascii=False)
        with (options.destination / 'DIAG.tsv').open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t')
            writer.writeheader()
            writer.writerows(rows)
        summary = ['', 'After replay (target-rule holds; reminder excluded):']
        for rule in 'abc':
            for expected in ('hold', 'pass'):
                selected = [row for row in rows if row['target_rule'] == rule and row['expect'] == expected]
                summary.append(f'Rule {rule}, expected {expected}: {sum(row["after_target_held"] for row in selected)}/{len(selected)} held.')
        for expected in ('hold', 'pass'):
            indices = [i for i, session in enumerate(sessions) if session['expect'] == expected]
            summary.append(f'All target rules, expected {expected}: {sum(rows[i]["after_target_held"] for i in indices)}/{len(indices)}; any rule finding: {sum(bool(rows[i]["after_rules"]) for i in indices)}/{len(indices)}; native holds including reminder: {sum(after[i]["held"] for i in indices)}/{len(indices)}.')
        report = options.destination / 'DIAG.md'
        baseline = report.read_text().split('\nAfter replay (target-rule holds; reminder excluded):')[0]
        report.write_text(baseline + '\n'.join(summary) + '\n')
        print('\n'.join(summary))
        return
    rows = []
    for index, (session, grade) in enumerate(zip(sessions, grades)):
        rows.append(dict(index=index, pair_id=session.get('pair_id', session.get('id', '')),
                         cause=session['cause'], kind=session['kind'], expect=session['expect'],
                         native_held=grade['held'], why_one_line=session['why_one_line'],
                         **explain(session, grade)))
    with (options.destination / 'DIAG.tsv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    summary = ['Script diagnosis of the supplied baseline; one TSV row per session.', '',
               'Rule holds exclude the four-question reminder. Denominators use expect, not kind.', '']
    for rule in 'abc':
        for expected in ('hold', 'pass'):
            selected = [row for row in rows if row['target_rule'] == rule and row['expect'] == expected]
            summary.append(f'Rule {rule}, expected {expected}: {sum(row["target_held"] for row in selected)}/{len(selected)} held.')
    summary += ['', 'Read review follows this scripted summary. Exact findings, reading identities, network records and reasons are in DIAG.tsv.']
    (options.destination / 'DIAG.md').write_text('\n'.join(summary) + '\n')


if __name__ == '__main__':
    main()
