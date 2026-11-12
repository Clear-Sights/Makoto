"""Replay a corpus through one variant of Makoto and record every decision.

    python3 eval/run_corpus.py --plugin DIR --corpus corpus.jsonl --out results.jsonl [--retries 2] [--clear]

DIR holds makoto2.py. Each session gets a fresh state directory and its events are sent in order through
makoto2.main, the same function the hook command runs. Per decision the output records `kind`:
hold (a rule d finding), error (Makoto's own infrastructure error, whether it blocked or only reported) or ok.
After every held Stop, `--retries` more copies of that Stop are sent with stop_hook_active true and recorded
as `retry` rows. With `--clear`, the run named by each held Stop is performed and the Stop is sent again.
"""
import argparse
import contextlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HOLD = re.compile(r'makoto rule (\w) \[[^\]]*\]: ')


def findings(reason):
    """(rule, subject) pairs from a hold message."""
    found = []
    for match in HOLD.finditer(reason):
        try:
            subject, _ = json.JSONDecoder().raw_decode(reason[match.end():])
        except ValueError:
            continue
        found.append((match.group(1), subject))
    return found


def clearing_events(base, subject, n):
    """The events that perform the action a hold names: one run of its subject."""
    tid = f'clear{n}'
    name, tool_input, response = ('Bash', {'command': 'python3 ' + str(subject)}, {'stdout': 'ok', 'stderr': '', 'interrupted': False, 'exitCode': 0})
    return [dict(base, hook_event_name='PreToolUse', tool_name=name, tool_input=tool_input, tool_use_id=tid),
            dict(base, hook_event_name='PostToolUse', tool_name=name, tool_input=tool_input, tool_use_id=tid, tool_response=response)]


def classify(response):
    reason = response.get('reason') or response.get('hookSpecificOutput', {}).get('permissionDecisionReason') or ''
    blocked = response.get('decision') == 'block' or response.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'
    message = response.get('systemMessage', '')
    if 'makoto infrastructure error' in reason or 'makoto infrastructure error' in message:
        return 'error', reason or message, blocked
    if blocked:
        return 'hold', reason, True
    if message.startswith('makoto'):
        return 'report', message, False
    return 'ok', '', False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plugin', required=True)
    ap.add_argument('--corpus', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--retries', type=int, default=0)
    ap.add_argument('--clear', action='store_true', help='after each held Stop, perform the named action and resend it')
    ap.add_argument('--corrupt-mid', action='store_true', help='tamper with the journal after the middle event')
    args = ap.parse_args()
    sys.path.insert(0, args.plugin)
    import makoto2 as m
    with open(args.corpus) as corpus, open(args.out, 'w') as out:
        for line in corpus:
            session = json.loads(line)
            rows = []
            with tempfile.TemporaryDirectory() as state:
                cfg = dict(m.CONFIG, state_dir=state, checkpoint=True)
                for i, event in enumerate(session['events']):
                    response = m.main(json.dumps(event), cfg)
                    kind, reason, blocked = classify(response)
                    if kind != 'ok':
                        rows.append({'i': i, 'kind': kind, 'blocked': blocked, 'reason': reason})
                    if args.corrupt_mid and i == len(session['events']) // 2:
                        journal = m.sigma_path(state, session['id'])
                        if journal.exists():
                            journal.write_text(journal.read_text().replace('hook_event_name', 'hook_event_nam3', 1))
                            with contextlib.suppress(OSError):
                                os.remove(str(journal) + '.ckpt')
                    if args.clear and kind == 'hold' and event['hook_event_name'] == 'Stop':
                        base = {'session_id': event['session_id'], 'cwd': event['cwd']}
                        for n, (_, subject) in enumerate(findings(reason)):
                            for step in clearing_events(base, subject, n):
                                m.main(json.dumps(step), cfg)
                        again = dict(event, stop_hook_active=True)
                        kind3, reason3, blocked3 = classify(m.main(json.dumps(again), cfg))
                        rows.append({'i': i, 'kind': 'clear', 'result': kind3, 'blocked': blocked3, 'reason': reason3})
                    if kind == 'hold' and event['hook_event_name'] == 'Stop':
                        for n in range(args.retries):
                            again = dict(event, stop_hook_active=True)
                            response = m.main(json.dumps(again), cfg)
                            kind2, reason2, blocked2 = classify(response)
                            rows.append({'i': i, 'kind': 'retry', 'n': n + 1, 'blocked': blocked2, 'result': kind2, 'reason': reason2})
            out.write(json.dumps({'id': session['id'], 'rows': rows}) + '\n')


if __name__ == '__main__':
    main()
