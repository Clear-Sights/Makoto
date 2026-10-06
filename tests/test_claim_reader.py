"""Independent records exercise claim boundaries and original-source freshness."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
from makoto2 import observed
from makoto2.claim_reader import read_claims
from makoto2.four_checks import lineage


def test_written_property_has_subject_and_values():
    event = dict(hook_event_name='PreToolUse', tool_name='Edit',
                 tool_input=dict(file_path='report.md', new_string='Current capacity is 27.'))
    claim = read_claims(observed.record([]), event)[0]
    assert claim['subject']
    assert '27' in claim['values']


def test_changed_original_needs_reading_after_change():
    read = dict(hook_event_name='PostToolUse', tool_name='Read',
                tool_input=dict(file_path='capacity.md'), tool_response='Capacity: 27.')
    change = dict(hook_event_name='PostToolUse', tool_name='Edit',
                  tool_input=dict(file_path='capacity.md', old_string='27', new_string='19'),
                  tool_response='edited')
    event = dict(hook_event_name='Stop', last_assistant_message='Current capacity is 27.')
    assert list(lineage(observed.record([read, change]), event, {}))
    fresh = dict(read, tool_response='Capacity: 19.')
    event['last_assistant_message'] = 'Current capacity is 19.'
    assert not list(lineage(observed.record([read, change, fresh]), event, {}))


def test_unverified_changed_property_is_silent():
    event = dict(hook_event_name='Stop', last_assistant_message='Current capacity is unverified; old value was 27.')
    assert not read_claims(observed.record([]), event)


def test_activity_mention_does_not_assert_a_current_verdict():
    old = dict(hook_event_name='PostToolUse', tool_name='Read',
               tool_input=dict(file_path='mode.txt'), tool_response='mode: running')
    new = dict(old, tool_response='mode: paused')
    event = dict(hook_event_name='Stop', last_assistant_message='Waiting before running the next measurement.')
    assert not list(lineage(observed.record([old, new]), event, {}))


def test_unique_parameter_names_failure_but_ambiguous_parameter_does_not():
    from makoto2.evaluate import _unnamed_failures
    response = 'FAILED tests/test_meter.py::test_reading[alpha]\n1 failed'
    event = dict(hook_event_name='PostToolUse', tool_name='Bash',
                 tool_input=dict(command='python3 -m pytest'),
                 tool_response=dict(exitCode=1, stdout=response))
    claim = dict(hook_event_name='Stop', last_assistant_message='1 test failed. alpha needs repair.')
    assert not _unnamed_failures(observed.record([event]), claim, dict(negation_window=30))
    event['tool_response']['stdout'] += '\nFAILED tests/test_scale.py::test_bound[alpha]\n2 failed'
    claim['last_assistant_message'] = '2 tests failed. alpha needs repair.'
    assert _unnamed_failures(observed.record([event]), claim, dict(negation_window=30))


def test_written_unverified_boolean_does_not_claim_a_decided_measurement():
    from makoto2.four_checks import findings
    failed = dict(hook_event_name='PostToolUse', tool_name='Bash',
                  tool_input=dict(command='meter query'),
                  tool_response=dict(exitCode=2, stdout='measurement unavailable'))
    event = dict(hook_event_name='PreToolUse', tool_name='Write',
                 tool_input=dict(file_path='measurement.json',
                                 content='{"exists":false,"evaluation":"unverified"}'))
    assert not list(findings(observed.record([failed]), event, {}))


def test_point_comparison_requires_the_same_subject():
    from makoto2.four_checks import other_point
    events = [dict(hook_event_name='PostToolUse', tool_name='Bash',
                   tool_input=dict(command='desktop-control --knob 5'),
                   tool_response='desktop control knob=5'),
              dict(hook_event_name='PostToolUse', tool_name='Read',
                   tool_input=dict(file_path='viewer-guide.txt'),
                   tool_response='Mobile viewer handles videos.')]
    event = dict(hook_event_name='Stop', last_assistant_message='The mobile viewer handles videos.')
    assert not list(other_point(observed.record(events), event, {}))


def test_unit_comparison_binds_the_metric_not_just_its_number():
    from makoto2.four_checks import spec
    events = [dict(hook_event_name='PostToolUse', tool_name='Bash',
                   tool_input=dict(command='measure payload'),
                   tool_response='metric=payload value=91 unit=bytes'),
              dict(hook_event_name='PostToolUse', tool_name='Bash',
                   tool_input=dict(command='measure duration'),
                   tool_response='metric=duration value=91 unit=seconds')]
    event = dict(hook_event_name='Stop', last_assistant_message='Duration is 91 seconds.')
    assert not list(spec(observed.record(events), event, {}))
