"""block_in: holds block inside the listed projects and only report outside them."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'plugin')]
from makoto2 import hook

WRITE = {'hook_event_name': 'PreToolUse', 'session_id': 's', 'tool_name': 'Write', 'tool_use_id': 'w',
         'tool_input': {'file_path': 'notes.md', 'content': 'See unread/path.md for details.'}}


def send(tmp_path, cwd, block_in):
    config = {'state_dir': str(tmp_path), 'adapter': 'inferred'}
    if block_in is not None:
        config['block_in'] = block_in
    return hook.main(json.dumps(dict(WRITE, cwd=cwd)), config)


def test_unset_blocks_everywhere(tmp_path):
    assert send(tmp_path, '/work/other', None)['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_inside_listed_project_still_blocks(tmp_path):
    assert send(tmp_path, '/home/user/makoto/plugin', ['/home/user/makoto'])['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_outside_listed_project_reports_without_blocking(tmp_path):
    response = send(tmp_path, '/home/user/other', ['/home/user/makoto'])
    assert 'hookSpecificOutput' not in response and 'decision' not in response
    assert 'makoto rule' in response['systemMessage']


def test_prefix_is_a_directory_not_a_name_prefix(tmp_path):
    response = send(tmp_path, '/home/user/makoto-dev-old', ['/home/user/makoto'])
    assert 'systemMessage' in response


def test_reported_step_counts_as_admitted_for_later_evidence(tmp_path):
    send(tmp_path, '/home/user/other', ['/home/user/makoto'])
    rows = [json.loads(line) for f in tmp_path.glob('*.jsonl') for line in f.read_text().splitlines()]
    assert rows[-1]['admitted'] is True and rows[-1]['findings']
