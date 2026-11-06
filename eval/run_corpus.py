"""Replay a corpus through one variant of Makoto and record every decision.

    python3 eval/run_corpus.py --plugin DIR --corpus corpus.jsonl --out results.jsonl [--block-in DIR] [--retries 2]

DIR holds makoto2.py. Each session gets a fresh state directory and its events are sent in order through
makoto2.main, the same function the hook command runs. Per decision the output records `kind`:
hold (rule finding), error (Makoto's own infrastructure error, whether it blocked or only reported) or ok.
After every held Stop, `--retries` more copies of that Stop are sent with stop_hook_active true and recorded
as `retry` rows, which is how the stop cap shows.
"""
import argparse
import json
import sys
import tempfile


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
    ap.add_argument('--block-in')
    ap.add_argument('--retries', type=int, default=0)
    args = ap.parse_args()
    sys.path.insert(0, args.plugin)
    import makoto2 as m
    with open(args.corpus) as corpus, open(args.out, 'w') as out:
        for line in corpus:
            session = json.loads(line)
            rows = []
            with tempfile.TemporaryDirectory() as state:
                cfg = dict(m.CONFIG, state_dir=state, checkpoint=True)
                if args.block_in:
                    cfg['block_in'] = [args.block_in]
                for i, event in enumerate(session['events']):
                    response = m.main(json.dumps(event), cfg)
                    kind, reason, blocked = classify(response)
                    if kind != 'ok':
                        rows.append({'i': i, 'kind': kind, 'blocked': blocked, 'reason': reason})
                    if kind == 'hold' and event['hook_event_name'] == 'Stop':
                        for n in range(args.retries):
                            again = dict(event, stop_hook_active=True)
                            response = m.main(json.dumps(again), cfg)
                            kind2, reason2, blocked2 = classify(response)
                            rows.append({'i': i, 'kind': 'retry', 'n': n + 1, 'blocked': blocked2, 'result': kind2, 'reason': reason2})
            out.write(json.dumps({'id': session['id'], 'rows': rows}) + '\n')


if __name__ == '__main__':
    main()
