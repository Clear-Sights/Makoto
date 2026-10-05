"""Representation changes must preserve the evidence boundary, not case wording."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'plugin'))

from makoto2 import family_lineage as lineage, family_other as other
from makoto2 import family_spec as spec, family_switch as switch, observed


def test_failure_counts_have_the_same_obligation_in_text_and_handoffs():
    record = observed.record([dict(hook_event_name='PostToolUse', tool_name='Bash',
        tool_input={'command':'verify inventory'},
        tool_response={'exitCode':1, 'stdout':'FAIL alpha\nFAIL beta'})])
    for text in ('2 failures', 'Two checks failed'):
        for event in (dict(hook_event_name='Stop', last_assistant_message=text),
                      dict(hook_event_name='PreToolUse', tool_name='Write',
                           tool_input={'file_path':'result.md', 'content':text})):
            assert any('C12' in f['entries'] for f in spec.spec_claim(record,event,{}))
            if event['hook_event_name']=='Stop':
                event['last_assistant_message'] += ': alpha and beta'
            else:
                event['tool_input']['content'] += ': alpha and beta'
            assert not spec.spec_claim(record,event,{})


def test_residue_branch_must_belong_to_the_match():
    code = 'for row in rows:\n m = re.match(pattern, row)\n if m:\n  accept(m)\n'
    event = dict(hook_event_name='PreToolUse',tool_name='Write',tool_input={'content':code})
    assert spec.spec_tree(observed.record([]),event,{})
    event['tool_input']['content'] += ' else:\n  residue.append(row)\n'
    assert not spec.spec_tree(observed.record([]),event,{})
    event['tool_input']['content'] = code + ' if debug:\n  trace(row)\n else:\n  trace(m)\n'
    assert spec.spec_tree(observed.record([]),event,{})


def test_reading_the_prior_artifact_pays_the_overwrite_obligation(tmp_path):
    path = str(tmp_path/'document.md')
    (tmp_path/'document.md').write_text('old')
    event = dict(hook_event_name='PreToolUse',tool_name='Write',cwd=str(tmp_path),
                 tool_input={'file_path':path,'content':'new'})
    assert other.other_write(observed.record([]),event,observed)
    record = observed.record([dict(hook_event_name='PostToolUse',tool_name='Read',
                                  tool_input={'file_path':path},tool_response='old')])
    assert not other.other_write(record,event,observed)


def test_constant_exports_are_not_unused_computations():
    assert not switch.switch_tree('LIMIT = 17')
    assert switch.switch_tree('result = compute()') == [('unused_result',1)]
    assert not switch.switch_tree('result = compute()\nconsume(result)')


def test_common_owner_imports_are_not_copied_implementations():
    first = dict(hook_event_name='PostToolUse',tool_name='Edit',
                 tool_input={'file_path':'a.py','new_string':'from owner import rule'},tool_response='ok')
    current = dict(hook_event_name='PreToolUse',tool_name='Edit',
                   tool_input={'file_path':'b.py','new_string':'from owner import rule'})
    assert not lineage.lineage_edit(observed.record([first]),current,observed)
    first['tool_input']['new_string'] = current['tool_input']['new_string'] = 'return rule(x, 17)'
    assert lineage.lineage_edit(observed.record([first]),current,observed)


def test_explicit_commit_citations_require_primary_readings():
    event = dict(hook_event_name='Stop',last_assistant_message='The fix is commit abc1234.')
    assert lineage.hook_lineage_refs(observed.record([]),event,observed)==['abc1234']
    primary = dict(hook_event_name='PostToolUse',tool_name='Bash',
                   tool_input={'command':'git log --oneline'},tool_response='abc1234 fix')
    assert not lineage.hook_lineage_refs(observed.record([primary]),event,observed)
    primary['tool_name']='Agent'
    assert lineage.hook_lineage_refs(observed.record([primary]),event,observed)==['abc1234']


def test_native_terms_table_uses_the_same_empty_binding_predicate():
    event = dict(hook_event_name='PreToolUse',tool_name='Write',tool_input={
        'file_path':'terms.md','content':'| term | check |\n| rule | |'})
    assert spec.spec_terms(observed.record([]),event,{})
    event['tool_input']['content'] = '| term | check |\n| rule | check_rule |'
    assert not spec.spec_terms(observed.record([]),event,{})


def test_shipment_status_is_distinct_from_a_modified_noun():
    record = observed.record([])
    assert spec.spec_claim(record, dict(hook_event_name='Stop', last_assistant_message='Shipped.'), {})
    assert not spec.spec_claim(record, dict(hook_event_name='Stop', last_assistant_message='The shipped package fails.'), {})


def test_revision_field_in_primary_measurement_pays_citation():
    record = observed.record([dict(hook_event_name='PostToolUse', tool_name='Bash',
        tool_input={'command':'measure'}, tool_response='revision=abc1234 value=8')])
    event = dict(hook_event_name='Stop', last_assistant_message='Measured value 8 for revision abc1234.')
    assert not lineage.hook_lineage_refs(record,event,observed)
