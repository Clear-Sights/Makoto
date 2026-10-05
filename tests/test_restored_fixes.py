"""Fixes from the seed-run branch (#133) that a conflict resolution dropped."""
import os, sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))
from makoto2 import hook, observed


def _obs(output):
    return SimpleNamespace(seq=3, tool="Bash", input={"command": "pytest"}, output=output,
                           exit=0, failed=False, objects={"t.py"}, written=set(),
                           created=set(), send="", search=None)


def test_changed_result_at_same_offset_fires_again():
    finding = {"row": "R1", "objects": ["t.py"]}
    _, first = hook.o_once(finding, SimpleNamespace(obs=[_obs("1 failed")]), set())
    found, second = hook.o_once(finding, SimpleNamespace(obs=[_obs("1 passed")]), {first})
    assert found is finding and second != first


def test_current_settled_event_joins_the_record():
    ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
          "tool_input": {"command": "ls"}, "tool_response": {"stdout": "a", "exit_code": 0}}
    assert len(observed.record([], ev).obs) == 1
    assert len(observed.record([], dict(ev, hook_event_name="PreToolUse")).obs) == 0


from makoto2 import family_lineage, family_other


def read(path, text):
    return dict(hook_event_name='PostToolUse', tool_name='Read',
                tool_input={'file_path': str(path)}, tool_response=text)


def write(tmp_path, name, text):
    return dict(hook_event_name='PreToolUse', tool_name='Write', cwd=str(tmp_path),
                tool_input={'file_path': name, 'content': text})


def test_asserted_sources_require_direct_reading(tmp_path):
    source = tmp_path/'policy.txt'
    source.write_text('Restricted.')
    report = write(tmp_path, 'summary.md', 'Use is permitted by policy.txt.\n')
    relay = dict(hook_event_name='PostToolUse', tool_name='Agent', tool_input={},
                 tool_response='policy.txt permits use.')
    assert family_lineage.hook_lineage_refs(observed.record([relay]), report, observed)
    assert not family_lineage.hook_lineage_refs(
        observed.record([relay, read(source, 'Restricted.')]), report, observed)
    input_only = dict(relay, tool_name='Bash',
                      tool_input={'command':'grep policy.txt'}, tool_response='no matches')
    assert family_lineage.hook_lineage_refs(observed.record([input_only]), report, observed)
    listing = dict(input_only, tool_input={'command': 'ls'}, tool_response='policy.txt')
    assert family_lineage.hook_lineage_refs(observed.record([listing]), report, observed)
    printed = dict(input_only, tool_input={'command': 'cat ' + str(source)},
                   tool_response='Restricted.')
    assert not family_lineage.hook_lineage_refs(observed.record([printed]), report, observed)
    report['tool_input']['content'] = 'SHA abcdef123456.'
    hash_read = dict(relay, tool_name='Bash', tool_response='abcdef123456' + '0' * 52)
    assert not family_lineage.hook_lineage_refs(observed.record([hash_read]), report, observed)
    report['tool_input']['content'] = 'SHA abcdef123457.'
    assert family_lineage.hook_lineage_refs(observed.record([hash_read]), report, observed)
    report['tool_input']['content'] = 'policy.txt is authoritative.\n'
    assert family_lineage.hook_lineage_refs(observed.record([]), report, observed)
    report['tool_input']['content'] = 'Remember policy.txt for later.\n'
    assert not family_lineage.hook_lineage_refs(observed.record([]), report, observed)


def test_explicit_inventory_allows_required_units_and_consumed_helpers(tmp_path):
    source = tmp_path/'contract.md'
    text = 'One unit required: parse_value.'
    source.write_text(text)
    record = observed.record([read(source, text)])
    report = write(tmp_path, 'parser.py',
                   'def parse_value(x): return helper(x)\ndef helper(x): return int(x)\n'
                   'def unrelated(x): return str(x)\n')
    assert family_lineage.lineage_units(record, report, observed) == ['unrelated']
    assert not family_lineage.lineage_units(observed.record([]), report, observed)


def test_preserving_whole_write_must_keep_unrelated_lines(tmp_path):
    source = tmp_path/'settings.txt'
    old = 'timeout: 3\n# operator note\ncustom: yes\n'
    source.write_text(old)
    user = dict(hook_event_name='UserPromptSubmit', prompt='Change timeout; preserve the rest.')
    record = observed.record([user, read(source, old)])
    report = write(tmp_path, 'settings.txt', 'timeout: 4\n')
    assert family_other.other_write(record, report, observed) == [('D11', str(source))]
    report['tool_input']['content'] = old.replace('3', '4')
    assert not family_other.other_write(record, report, observed)
    record = observed.record([dict(user, prompt='Replace this file with only the timeout.'), read(source, old)])
    report['tool_input']['content'] = 'timeout: 4\n'
    assert not family_other.other_write(record, report, observed)


def test_absence_requires_independent_probe_when_observed_basis_is_unpaid(tmp_path):
    event = dict(hook_event_name='Stop', cwd=str(tmp_path), last_assistant_message='Result is clean.')
    failed = dict(hook_event_name='PostToolUse', tool_name='Bash',
                  tool_input={'command': 'probe'}, tool_response='Exit code 2\nunavailable')
    assert family_lineage.lineage_absence(observed.record([failed]), event, observed)
    assert not family_lineage.lineage_absence(observed.record([]), event, observed)
    success = dict(failed, tool_response='Exit code 0')
    assert not family_lineage.lineage_absence(observed.record([failed, success]), event, observed)
    source = tmp_path/'report.md'
    source.write_text('Result is clean.')
    event['last_assistant_message'] = 'report.md proves the result is clean.'
    record = observed.record([read(source, 'Result is clean.')])
    assert family_lineage.lineage_absence(record, event, observed)
    event['last_assistant_message'] = 'Result is unknown; remember report.md for later.'
    assert not family_lineage.lineage_absence(record, event, observed)
