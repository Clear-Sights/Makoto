"""Independent source/version fixtures: no benchmark case text."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
from makoto2 import observed
from makoto2.family_lineage import lineage_provenance


def read(path, value):
    return dict(hook_event_name='PostToolUse', tool_name='Read', tool_input={'file_path': path}, tool_response=value)


def run(command, value):
    return dict(hook_event_name='PostToolUse', tool_name='Bash', tool_input={'command': command}, tool_response=value)


def claim(text):
    return dict(hook_event_name='Stop', last_assistant_message=text)


def test_superseded_value_and_latest_read():
    events = [read('capacity.txt', 'Capacity: 76.'), read('capacity.txt', 'Capacity: 24.')]
    assert lineage_provenance(observed.record(events), claim('Current capacity is 76.'), observed)
    assert not lineage_provenance(observed.record(events), claim('Current capacity is 24.'), observed)
    assert not lineage_provenance(observed.record(events), claim('Old capacity 76 is unverified.'), observed)


def test_edit_invalidates_value_without_reading_disk():
    events = [read('capacity.txt', 'Capacity: 76.'), dict(hook_event_name='PostToolUse', tool_name='Edit', tool_input={'file_path':'capacity.txt', 'old_string':'76', 'new_string':'24'}, tool_response='edited')]
    assert lineage_provenance(observed.record(events), claim('Current capacity is 76.'), observed)
    assert not lineage_provenance(observed.record(events + [read('capacity.txt', 'Capacity: 24.')]), claim('Current capacity is 24.'), observed)


def test_command_observation_and_subject_update():
    events = [run('quota show', 'approved EUR 840'), run('quota refresh', 'approval updated; approved EUR 620')]
    assert lineage_provenance(observed.record(events), claim('Current approved quota: EUR 840.'), observed)
    events += [run('quota show', 'approved EUR 620')]
    assert not lineage_provenance(observed.record(events), claim('Current approved quota: EUR 620.'), observed)


def test_receipt_after_subject_replacement():
    events = [read('receipt.txt', 'Snapshot verified 432 objects.'), run('store status', 'store recreated; old verification snapshot unavailable')]
    assert lineage_provenance(observed.record(events), claim('Current store has 432 verified objects.'), observed)
    assert not lineage_provenance(observed.record(events), claim('432 is unverified for the current store.'), observed)
    events += [run('store verify', 'current store 431 objects; verification complete')]
    assert not lineage_provenance(observed.record(events), claim('Current store has 431 verified objects.'), observed)


def test_relay_citation_requires_original():
    events = [read('summary.txt', 'All methods supported. Source claimed: methods.txt.')]
    assert lineage_provenance(observed.record(events), claim('All methods supported, according to the prior answer.'), observed)
    events += [read('methods.txt', 'Only retrieval methods supported.')]
    assert not lineage_provenance(observed.record(events), claim('Only retrieval methods supported.'), observed)


def test_receipt_replacement_requires_same_claim_subject():
    events = [read('receipt.txt', 'Snapshot verified 432 objects.'), run('build status', 'old build removed')]
    assert not lineage_provenance(observed.record(events), claim('Store has 432 verified objects.'), observed)


def test_unrelated_number_cannot_refresh_superseded_measurement():
    events = [read('capacity.txt', 'Capacity: 76.'), read('capacity.txt', 'Capacity: 24.'), read('inventory.txt', 'Inventory: 76.')]
    assert lineage_provenance(observed.record(events), claim('Current capacity is 76.'), observed)


def test_changed_verdict_and_named_value():
    events = [read('check.txt', 'Result: passed. Owner: Mira.'), read('check.txt', 'Result: failed. Owner: Jae.')]
    assert lineage_provenance(observed.record(events), claim('Current result is passed.'), observed)
    assert lineage_provenance(observed.record(events), claim('Current owner is Mira.'), observed)
    assert not lineage_provenance(observed.record(events), claim('Current result is failed. Current owner is Jae.'), observed)


def test_historical_value_and_subject_local_unverified():
    events = [read('capacity.txt', 'Capacity: 76.'), read('capacity.txt', 'Capacity: 24.')]
    assert not lineage_provenance(observed.record(events), claim('Earlier capacity was 76. Current capacity is 24.'), observed)
    assert lineage_provenance(observed.record(events), claim('Current capacity is 76. Stock is unverified.'), observed)


def test_displayed_change_text_does_not_invalidate_another_command():
    events = [run('cd work && grep -n rule source.py', '301: rule changed'), run('cd work && cat report.txt', 'rule changed; result 8')]
    assert not lineage_provenance(observed.record(events), claim('The source listing has line 301.'), observed)


def test_time_value_is_not_a_number_fragment():
    events = [read('schedule.txt', 'Time: 04:30.'), read('schedule.txt', 'Time: 05:00.')]
    assert not lineage_provenance(observed.record(events), claim('There are 04 examples.'), observed)
    assert lineage_provenance(observed.record(events), claim('Current time is 04:30.'), observed)


def test_primary_iso_timestamp_pays_minute_projection():
    from makoto2.evaluate import number_pays
    obs = observed.record([run('log-reader', '2027-02-03T12:15:42.183Z endpoint error')]).obs[0]
    assert number_pays({}, {}, obs)('12:15')


def test_requirement_text_is_not_a_verification_receipt():
    events = [run('cat rules.txt', 'All 19 checks must be verified. Every snapshot must be signed.'), run('store replace', 'snapshot replaced; old verification snapshot unavailable')]
    assert not lineage_provenance(observed.record(events), claim('The store has 19 checks.'), observed)


def test_communicated_value_is_not_a_test_verdict():
    from makoto2.family_spec import claims
    r = observed.record([run('tests', 'Exit code 1\n1 failed')])
    assert not any(c.kind in ('pass', 'count') for c in claims('I passed along one value from a colleague.', r))
