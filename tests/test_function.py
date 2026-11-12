"""The rest of Makoto's function: what pays rule d, what it does not hold, and the one adapter (through hooks.json)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_lean2 as base  # noqa: E402
from test_lean2 import held  # noqa: E402


def test_a_full_read_pays_an_edited_config_file_and_a_slice_does_not(tmp_path):
    s = base.Session(tmp_path)
    s.write('settings.json', '{"a": 1}\n')
    s.call('Read', {'file_path': 'settings.json', 'limit': 1}, {'content': '{"a": 1}'})
    assert held(s.stop())
    s.call('Read', {'file_path': 'settings.json'}, {'content': '{"a": 1}'})
    assert s.stop() == {}


def test_a_commit_or_push_is_never_held_but_the_final_answer_still_is(tmp_path):
    s = base.Session(tmp_path)
    s.write('app/mod.py', 'x = 1\n')
    for command in ('git commit -am wip', 'git push origin main'):
        s.call('Bash', {'command': command}, {'stdout': '', 'exitCode': 0})
    assert held(s.stop())


def test_a_final_answer_is_held_only_for_its_own_agents_edits(tmp_path):
    s = base.Session(tmp_path)
    tool_input = {'file_path': 'worker.py', 'content': 'x = 1\n'}
    for event in (s.ev('PreToolUse', agent_id='w1', tool_name='Write', tool_use_id='w', tool_input=tool_input),
                  s.ev('PostToolUse', agent_id='w1', tool_name='Write', tool_use_id='w', tool_input=tool_input, tool_response={'content': 'ok'})):
        base.send(tmp_path, event)
    other = base.send(tmp_path, s.ev('SubagentStop', agent_id='w2', last_assistant_message='Done'))
    own = base.send(tmp_path, s.ev('SubagentStop', agent_id='w1', last_assistant_message='Done'))
    assert other == {} and held(own)


def test_a_run_that_failed_still_pays_because_its_output_was_read(tmp_path):
    s = base.Session(tmp_path)
    s.write('app/mod.py', 'raise SystemExit(1)\n')
    s.call('Bash', {'command': 'python3 app/mod.py'}, {'stdout': '', 'stderr': 'exit\n', 'exitCode': 1})
    assert s.stop() == {}


def test_a_deleted_file_is_no_longer_held(tmp_path):
    s = base.Session(tmp_path)
    s.write('app/mod.py', 'x = 1\n')
    s.call('Bash', {'command': 'rm app/mod.py'}, {'stdout': '', 'exitCode': 0})
    assert s.stop() == {}
