"""Independent label for a hold, per eval/RULES2.md. Never imports Makoto.

    python3 eval/independent.py corpus.jsonl sample.json

sample.json is the output of eval/sample.py. Prints one line per hold and the false-positive share with its
Wilson interval. A hold is a false positive iff every one of its findings is present (the reading was not missing).
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stats import show  # noqa: E402

READING = ('Read', 'Grep', 'Glob', 'Bash', 'WebFetch', 'WebSearch')
FILE_TOOLS = ('Read', 'Write', 'Edit', 'MultiEdit', 'NotebookEdit')
EDIT_TOOLS = ('Write', 'Edit', 'MultiEdit', 'NotebookEdit')
NETWORK = re.compile(r'curl|wget|pip |npm |gh |git ls-remote|http')
FINDING = re.compile(r'makoto rule (\w) \[[^\]]*\]: ')


def word(char):
    return char.isalnum() or char == '_'


def present_in(subject, text):
    """subject occurs in text, with a non-word character (or the text edge) outside each word-character end."""
    start = text.find(subject)
    while start != -1:
        end = start + len(subject)
        left_ok = start == 0 or not word(subject[0]) or not word(text[start - 1])
        right_ok = end == len(text) or not word(subject[-1]) or not word(text[end])
        if left_ok and right_ok:
            return True
        start = text.find(subject, start + 1)
    return False


def flat(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return ' '.join(flat(v) for v in value.values())
    if isinstance(value, list):
        return ' '.join(flat(v) for v in value)
    return '' if value is None else str(value)


def findings(reason):
    found = []
    for match in FINDING.finditer(reason):
        try:
            subject, _ = json.JSONDecoder().raw_decode(reason[match.end():])
        except ValueError:
            continue
        found.append((match.group(1), subject if isinstance(subject, str) else json.dumps(subject)))
    return found


def pathlike(subject):
    return '/' in subject or (not subject.startswith('.') and re.search(r'\.[A-Za-z0-9]{1,5}$', subject) is not None)


def responses(before):
    return [flat(e.get('tool_response')) for e in before if e['hook_event_name'] == 'PostToolUse']


def produced(before):
    out = []
    for e in before:
        if e['hook_event_name'] == 'PreToolUse' and e['tool_name'] in EDIT_TOOLS + ('Bash',):
            out.append(flat(e['tool_input']))
    return out


def present(events, index, rule, subject):
    before = events[:index]
    if rule == 'a':
        return any(e['hook_event_name'] == 'PostToolUse' and e['tool_name'] in READING and flat(e.get('tool_response')).strip()
                   for e in before)
    if rule == 'c':
        start = max([i for i, e in enumerate(before) if e['hook_event_name'] == 'UserPromptSubmit'] or [-1]) + 1
        return any((e['hook_event_name'] in ('PreToolUse', 'PostToolUse') and (e['tool_name'] in ('WebFetch', 'WebSearch') or (
            e['tool_name'] == 'Bash' and NETWORK.search(str(e.get('tool_input', {}).get('command', ''))))))
            and subject in flat(e.get('tool_input')) + flat(e.get('tool_response')) for e in before[start:])
    if rule == 'd':
        base = subject.replace('\\', '/').rsplit('/', 1)[-1]
        last = None
        for i, e in enumerate(before):
            if e['hook_event_name'] == 'PreToolUse' and base in flat(e.get('tool_input')) and (
                    e['tool_name'] in EDIT_TOOLS or (e['tool_name'] == 'Bash' and re.search(r'>|tee|sed -i|cp |mv |touch', e['tool_input'].get('command', '')))):
                last = i
        if last is None:
            return False
        return any(e['hook_event_name'] == 'PostToolUse' and e['tool_name'] == 'Bash' and base in str(e.get('tool_input', {}).get('command', ''))
                   and flat(e.get('tool_response')).strip() for e in before[last + 1:])
    # rule b, and any other rule, is a name
    if pathlike(subject):
        for e in before:
            if e['hook_event_name'] == 'PreToolUse':
                target = str(e['tool_input'].get('file_path', ''))
                if e['tool_name'] in FILE_TOOLS and (target == subject or target.endswith('/' + subject)):
                    return True
                if e['tool_name'] == 'Bash' and subject in str(e['tool_input'].get('command', '')):
                    return True
    texts = responses(before) + produced(before) + [flat(e.get('prompt')) for e in before if e['hook_event_name'] == 'UserPromptSubmit']
    return any(present_in(subject, t) for t in texts)


def judge(events, index, reason):
    result = []
    for rule, subject in findings(reason):
        result.append((rule, subject, present(events, index, rule, subject)))
    return result


def main():
    corpus = {}
    with open(sys.argv[1]) as handle:
        for line in handle:
            row = json.loads(line)
            corpus[row['id']] = row
    sample = json.load(open(sys.argv[2]))
    false_positives, causes = 0, Counter()
    for item in sample['holds']:
        events = corpus[item['id']]['events']
        verdicts = judge(events, item['i'], item['reason'])
        fp = bool(verdicts) and all(p for _, _, p in verdicts)
        false_positives += fp
        if fp:
            for rule, subject, _ in verdicts:
                causes[(rule, subject)] += 1
        print(('FP  ' if fp else 'true'), item['id'][:8], item['i'], [(r, s[:40], 'present' if p else 'missing') for r, s, p in verdicts])
    print(json.dumps({'sampled': len(sample['holds']), 'false_positives': false_positives,
                      'share': show(false_positives, len(sample['holds'])),
                      'causes': {f'{r}:{s}': n for (r, s), n in causes.items()}}, indent=1))


if __name__ == '__main__':
    main()
