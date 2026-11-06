"""Build the corpus: Claude Code stream-json logs and session transcripts -> Makoto hook events, by script only.

    python3 eval/corpus.py --tiller DIR --local DIR --out corpus.jsonl

DIR for --tiller is a checkout of Clear-Sights/Tiller-from-the-Ashes (branch principles). Its packed ledgers are
read in memory, never unpacked to disk. One output line per session: {"id", "source", "prompt_known", "events"}.
Events are UserPromptSubmit (only where a sibling feed.json records the goal), PreToolUse, PostToolUse or
PostToolUseFailure, and a final Stop. Sessions with no tool call are dropped and counted.
"""
import argparse
import glob
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

GOAL = re.compile(r'^goal \| (.*?) \| reads=', re.S)


def parse(text):
    rows = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def flat(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ' '.join(c.get('text', '') for c in content if isinstance(c, dict))
    return str(content)


def response(name, tool_input, content, error):
    text = flat(content)
    if name == 'Bash':
        return {'stdout': text if not error else '', 'stderr': text if error else '', 'interrupted': False,
                'exitCode': 1 if error else 0}
    if name == 'Read':
        return {'type': 'text', 'file': {'filePath': tool_input.get('file_path', ''), 'content': text}}
    return {'content': text}


def events_of(rows, session, cwd, prompt):
    events = []
    base = {'session_id': session, 'cwd': cwd}
    if prompt:
        events.append(dict(base, hook_event_name='UserPromptSubmit', prompt=prompt))
    open_calls, last_text = {}, ''
    for row in rows:
        message = row.get('message')
        content = message.get('content') if isinstance(message, dict) else None
        if row.get('type') == 'assistant' and isinstance(content, list):
            for block in content:
                if block.get('type') == 'tool_use':
                    open_calls[block['id']] = (block['name'], block.get('input', {}))
                    events.append(dict(base, hook_event_name='PreToolUse', tool_name=block['name'],
                                       tool_input=block.get('input', {}), tool_use_id=block['id']))
                elif block.get('type') == 'text' and block.get('text', '').strip():
                    last_text = block['text']
        elif row.get('type') == 'user' and isinstance(content, list):
            structured = row.get('tool_use_result', row.get('toolUseResult'))
            for block in content:
                if block.get('type') == 'tool_result' and block.get('tool_use_id') in open_calls:
                    name, tool_input = open_calls.pop(block['tool_use_id'])
                    error = bool(block.get('is_error'))
                    event = dict(base, hook_event_name='PostToolUseFailure' if error else 'PostToolUse',
                                 tool_name=name, tool_input=tool_input, tool_use_id=block['tool_use_id'])
                    if error:
                        event['error'] = flat(block.get('content'))
                    else:
                        # The host's own structured result when the log kept it; otherwise a plain stand-in.
                        event['tool_response'] = structured if isinstance(structured, dict) and len(content) == 1 \
                            else response(name, tool_input, block.get('content'), False)
                    events.append(event)
    events.append(dict(base, hook_event_name='Stop', last_assistant_message=last_text, stop_hook_active=False))
    # The replay has no files: record the log's own fact that a Write onto an existing file (result type
    # `update`) targeted a file that existed. A hook on a live machine checks the file system instead.
    kind = {e['tool_use_id']: e.get('tool_response', {}).get('type') for e in events
            if e['hook_event_name'] == 'PostToolUse' and e['tool_name'] == 'Write' and isinstance(e.get('tool_response'), dict)}
    for e in events:
        if e['hook_event_name'] == 'PreToolUse' and e['tool_name'] == 'Write':
            e['makoto'] = {'target_exists': kind.get(e['tool_use_id']) == 'update'}
    return events


def session_of(rows, fallback):
    for row in rows:
        if row.get('session_id') or row.get('sessionId'):
            return row.get('session_id') or row['sessionId']
    return fallback


def cwd_of(rows):
    for row in rows:
        if row.get('cwd'):
            return row['cwd']
    return '/work'


def tiller(root):
    for ledger in sorted(glob.glob(str(Path(root) / 'research/raw/**/*.ledger.jsonl.gz'), recursive=True)):
        contents, entries = {}, []
        for line in gzip.open(ledger, 'rt'):
            record = json.loads(line)
            if 'path' in record:
                entries.append(record)
            else:
                contents[record['blob']] = record
        goals = {}
        for entry in entries:
            if entry['path'].endswith('.feed.json') and 'blob' in entry:
                match = GOAL.match(contents.get(entry['blob'], {}).get('text', ''))
                if match:
                    goals[entry['path'][:-len('.feed.json')]] = match.group(1).strip()
        for entry in entries:
            name = entry['path'].rsplit('/', 1)[-1]
            if re.fullmatch(r'goal-\d+\.jsonl', name) and 'blob' in entry:
                run_dir = entry['path'].rsplit('/', 1)[0]
                prompt = goals.get(run_dir[:-len('.run')] if run_dir.endswith('.run') else run_dir)
                yield entry['path'], contents[entry['blob']].get('text', ''), prompt


def local(root):
    for path in sorted(glob.glob(str(Path(root) / '*.jsonl'))):
        yield path, Path(path).read_text(encoding='utf-8', errors='replace'), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tiller')
    ap.add_argument('--local')
    ap.add_argument('--exclude', action='append', default=[], help='session ids to leave out (this session)')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    seen, stats = set(), {'logs': 0, 'duplicate': 0, 'no_tool_call': 0, 'kept': 0, 'with_prompt': 0}
    with open(args.out, 'w') as out:
        for source, iterator in (('tiller', tiller(args.tiller) if args.tiller else []),
                                 ('local', local(args.local) if args.local else [])):
            for path, text, prompt in iterator:
                stats['logs'] += 1
                rows = parse(text)
                session = session_of(rows, hashlib.sha256(text.encode()).hexdigest()[:16])
                key = (session, hashlib.sha256(text.encode()).hexdigest())
                if session in seen or session in args.exclude:
                    stats['duplicate'] += 1
                    continue
                seen.add(session)
                events = events_of(rows, session, cwd_of(rows), prompt)
                if not any(e['hook_event_name'] == 'PreToolUse' for e in events):
                    stats['no_tool_call'] += 1
                    continue
                stats['kept'] += 1
                stats['with_prompt'] += bool(prompt)
                out.write(json.dumps({'id': session, 'source': source + ':' + path, 'prompt_known': bool(prompt), 'events': events}) + '\n')
    print(json.dumps(stats))


if __name__ == '__main__':
    sys.exit(main())
