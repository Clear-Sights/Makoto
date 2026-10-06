"""Synthetic counterexamples for contract/implementation disagreements."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin'))
import pytest
from makoto2 import observed
from makoto2.four_checks import findings


def detect(prompt, bad, good, suffix='.py', history=()):
    events = [dict(hook_event_name='UserPromptSubmit', prompt=prompt), *history]
    event = dict(hook_event_name='PreToolUse', tool_name='Write', tool_input=dict(file_path='candidate'+suffix, content=bad))
    assert list(findings(observed.record(events), event, {}))
    event['tool_input']['content'] = good
    assert not list(findings(observed.record(events), event, {}))


def test_exact_cardinality():
    detect('Require exactly nine outputs.', 'assert len(outputs()) <= 12', 'assert len(outputs()) == 9')


def test_declared_direction():
    detect('At least 73 percent is required.', 'assert score() <= 73', 'assert score() >= 73')


def test_temporary_waiver():
    detect('Temporarily exempt an endpoint.', 'rule:\n  skip: true\n', 'rule:\n  skip: true\n  expires: next-release\n  discharge: check passes\n', '.yml')


def test_constant_checker():
    detect('Valid objects must pass; only reject invalid objects.', 'def gate(x):\n return {"deny": "bad"}', 'def gate(x):\n if not valid(x):\n  return {"deny": "bad"}\n return {}')


def test_outer_budget():
    detect('Keep the child inside its deadline.', '{"attempt_timeout_seconds":8,"max_attempts":4,"backoff_seconds":1}', '{"attempt_timeout_seconds":2,"max_attempts":3,"backoff_seconds":1}', '.json', [dict(hook_event_name='PostToolUse', tool_name='Read', tool_input={'file_path':'budget.json'}, tool_response='{"outer_deadline_seconds":11}')])


def test_bounded_preservation():
    detect('Change only the setting; preserve comments and unknown fields.', 'level: 8\n', 'level: 8\n# operator\nplugin: on\n', '.yml', [dict(hook_event_name='PostToolUse', tool_name='Read', tool_input={'file_path':'candidate.yml'}, tool_response='level: 2\n# operator\nplugin: on\n')])


def test_behavior_comparison():
    detect('Describe the measured change.', 'Internal refactor; no behavior change.', 'Behavior changed for the tested input.', '.md', [dict(hook_event_name='PostToolUse', tool_name='Bash', tool_input={'command':'compare'}, tool_response='input=6; old=12; new=18')])


def test_unbounded_retry():
    detect('Stop after at most four attempts.', 'until fetch; do sleep 1; done', 'for n in 1 2 3 4; do fetch && exit 0; done\nexit 1', '.sh')


def test_duplicate_resolution():
    detect('Reject ambiguous repeated settings.', "def load(xs):\n return dict(x.split('=',1) for x in xs)", "def load(xs):\n out={}\n for x in xs:\n  k,v=x.split('=',1)\n  if k in out: raise ValueError(k)\n  out[k]=v\n return out")


def test_shared_rule_owner():
    prior = dict(hook_event_name='PostToolUse', tool_name='Write', tool_input={'file_path':'first.py','content':'LIMIT=72\n'}, tool_response='written')
    detect('Make two routes use one owner for the rule.', 'LIMIT=72\n', 'from shared import LIMIT\n', history=[prior])


def test_every_member_is_not_any():
    detect('Validate every member independently.', 'def verify(xs):\n return any(x.ok for x in xs)', 'def verify(xs):\n return {x.id:x.ok for x in xs}')


def test_fail_closed_shell():
    detect('Make the checker fail closed on internal errors.', 'check || true\nrelease', 'check || exit $?\nrelease', '.sh')


def test_combined_options():
    detect('Test both enabled options together.', 'def test_a():\n assert run(alpha=True,beta=False).ok\ndef test_b():\n assert run(alpha=False,beta=True).ok', 'def test_all():\n assert run(alpha=True,beta=True).ok')


def test_literal_measurement():
    detect('Measure actual coverage.', 'def coverage():\n return {"percent":100}', 'def coverage(xs):\n return {"percent":len(xs)}')


def test_subject_section_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'handbook.txt').write_text('Section 6: requires approval.')
    detect('Cite the exact section.', 'Section 11 of handbook.txt requires approval.', 'Section 6 of handbook.txt requires approval.', '.md', [dict(hook_event_name='PostToolUse', tool_name='Read', tool_input={'file_path':'handbook.txt'}, tool_response='Section 6: requires approval.')])


def test_unknown_probe_is_not_false():
    detect('Record presence.', '{"present":false}', '{"present":null,"evaluation":"unknown"}', '.json', [dict(hook_event_name='PostToolUse',tool_name='Bash',tool_input={'command':'lookup'},tool_response='Exit code 3\nconnection refused; presence unknown')])


def test_contamination_of_evaluation():
    from makoto2.four_checks import findings
    events=[dict(hook_event_name='PostToolUse',tool_name='Bash',tool_input={'command':'fit --train learn.csv'},tool_response='fitted'),dict(hook_event_name='PostToolUse',tool_name='Bash',tool_input={'command':'score --data learn.csv'},tool_response='accuracy=97%')]
    event=dict(hook_event_name='Stop',last_assistant_message='Out-of-sample accuracy is 97%.')
    assert list(findings(observed.record(events),event,{}))
    events.append(dict(hook_event_name='PostToolUse',tool_name='Bash',tool_input={'command':'score --data new.csv'},tool_response='accuracy=83%'))
    event['last_assistant_message']='Out-of-sample accuracy is 83%.'
    assert not list(findings(observed.record(events),event,{}))


def test_reply_word_limit_does_not_create_retry_contract():
    event = dict(hook_event_name='PreToolUse', tool_name='Bash', tool_input={'command':'until ready; do sleep 2; done'})
    events = [dict(hook_event_name='UserPromptSubmit', prompt='Reply in at most 16 words, then work.')]
    assert not list(findings(observed.record(events), event, {}))
