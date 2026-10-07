"""Step 4 plants: NAME forms, precision-only exclusions and output references."""
import pytest

from test_shapes import Session, event, pair, output
from makoto2.precision import extract, names
from run_pairs import held


# Ten forms, each independently held when unread and cleared by source bytes.
NAME_FORMS = [
    ('path', './new-project/report-file.txt'),
    ('url', 'https://example.test/unread'),
    ('email', 'reader+new@example.test'),
    ('snake_case', 'unread_subject'),
    ('camelCase', 'unreadSubject'),
    ('dotted_module', 'unread.module'),
    ('hash', 'b5c1616'),
    ('uuid', '550e8400-e29b-41d4-a716-446655440000'),
    ('version', '1.2.3'),
    ('alphanumeric_id', 'subject91'),
]


@pytest.mark.parametrize('form,value', NAME_FORMS, ids=[f for f, _ in NAME_FORMS])
@pytest.mark.parametrize('wrapper', ['{}', '`{}`', '"{}"', '‘{}’'])
def test_each_name_form_unread_and_read(tmp_path, form, value, wrapper):
    text = wrapper.format(value)
    spans = names(text)
    assert value in [s.text for s in spans]
    assert all(s.text == text[s.start:s.end] for s in spans)
    s = Session(tmp_path)
    s.feed(pair())
    assert held(s.send(output(text)))
    assert 'a' in s.rules()
    assert any(f['rule'] == 'a' and f['subject'] == value for f in s.journal()[-1]['findings'])
    s.feed(pair(text=value, tid='name'))
    response = s.send(output(text))
    if form == 'url':
        assert held(response) and s.rules() == {'b'}
        s.feed(pair('WebFetch', {'url': value}, value, tid='web'))
        assert not held(s.send(output(text)))
    else:
        assert not held(response), response


@pytest.mark.parametrize('value', [
    'nondictionaryword', '日本語', 'ordinary', 'defaced', 'acceded', 'well-considered', 'twenty-three',
    '731', '-731', '+731', '1.5', '1.5kg', '12ms', '2 ms', '2 ms/kg',
    '19 °C', '3.5%', '1/2', '2026-10-06T19:24Z',
    '"exact phrase"', '`plain words`', '‘twenty-three’', '"731"', '`1.5kg`',
    '```py\nx = 19\n```', 'Error: file not found',
])
def test_precision_values_and_words_do_not_trigger_b(tmp_path, value):
    assert names(value) == []
    s = Session(tmp_path)
    s.feed(pair())
    response = s.send(output(value))
    plain = {'nondictionaryword', '日本語', 'ordinary', 'defaced', 'acceded',
             'well-considered', 'twenty-three', 'Error: file not found', '1/2'}
    assert s.rules() == (set() if value in plain else {'a'})
    assert held(response) == (value not in plain)
    s.feed(pair(text=value, tid='literal'))
    assert not held(s.send(output(value)))


@pytest.mark.parametrize('value', ['731', '2 ms/kg', 'twenty-three', 'nondictionaryword', '"exact phrase"', '```py\nx = 19\n```'])
def test_excluded_names_remain_general_precision(value):
    assert extract(value)
    assert names(value) == []


@pytest.mark.parametrize('boundary', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit'])
def test_current_writer_target_is_output_without_prompt_or_read(tmp_path, boundary):
    s = Session(tmp_path)
    s.feed(pair())
    ev = output('source data', boundary)
    assert not held(s.send(ev))
    assert any(w.get('output') and w['span'] == 'out.txt' for w in s.journal()[-1]['snapshot'])


@pytest.mark.parametrize('writer', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'Bash'])
@pytest.mark.parametrize('reference', ['out.txt', './out.txt', '/w/out.txt', '`out.txt`', 'Saved out.txt'])
def test_written_or_edited_file_in_final_is_output(tmp_path, writer, reference):
    s = Session(tmp_path)
    s.feed(pair())
    ev = output('source data', writer) if writer != 'Bash' else event('PreToolUse', tool_name='Bash', tool_use_id='write', tool_input={'command': 'touch out.txt'})
    assert not held(s.send(ev))
    s.send(dict(ev, hook_event_name='PostToolUse', tool_response={'content': 'ok', 'exitCode': 0}))
    if writer == 'NotebookEdit':
        # Execution pays d; the separate file read below establishes its state.
        s.feed(pair('NotebookExecute', {'notebook_path': 'out.txt'}, 'source data', tid='run'))
    s.feed(pair(ti={'file_path': 'out.txt'}, text='source data', tid='readback'))
    assert not held(s.send(output(reference)))
    assert s.rules() == set()


def test_output_reference_still_needs_original_artifact(tmp_path):
    s = Session(tmp_path)
    s.feed(pair())
    ev = output('source data', 'Write')
    assert not held(s.send(ev))
    s.send(dict(ev, hook_event_name='PostToolUse', tool_response={'content': 'ok'}))
    # Invalidate the only original reading with a native write acknowledgment.
    # A Bash mutation's run response would itself be an artifact reading.
    change = output('source data', 'Write', tid='stale')
    change['tool_input']['file_path'] = 'source.txt'
    assert not held(s.send(change))
    s.send(dict(change, hook_event_name='PostToolUse', tool_response={'content': 'ok'}))
    s.feed(pair(ti={'file_path': 'out.txt'}, text='source data', tid='out-readback'))
    s.feed(pair(ti={'file_path': 'source.txt'}, text='source data', tid='source-readback'))
    for retry in (False, True):
        # DESIGN D4: the readback establishes its own file, without sourcing its bytes.
        assert not held(s.send(dict(output('out.txt'), stop_hook_active=retry)))
        assert s.rules() == set()


def test_output_exemption_cannot_hide_unread_name_in_content(tmp_path):
    s = Session(tmp_path)
    s.feed(pair())
    assert held(s.send(output('unread_subject', 'Write')))
    assert {f['subject'] for f in s.journal()[-1]['findings'] if f['rule'] == 'a'} == {'unread_subject'}


def test_own_file_contents_never_pay_unread_names(tmp_path):
    s = Session(tmp_path)
    s.feed(pair())
    ev = output('unread_subject', 'Write')
    # Old executed writes can exist in an imported host record.
    from makoto2.provenance import Ledger
    from makoto2.evaluate import evaluate
    ledger = Ledger()
    for prior in pair():
        ledger.ingest(prior)
    ledger.ingest(ev)
    ledger.ingest(dict(ev, hook_event_name='PostToolUse', tool_response={'content': 'ok'}))
    for prior in pair(ti={'file_path': 'out.txt'}, text='unread_subject', tid='own'):
        ledger.ingest(prior)
    findings, _ = evaluate(ledger, output('out.txt unread_subject'))
    # An unrelated reading cannot supply origin for a literal copied from own output.
    assert {f['rule'] for f in findings} == {'a', 'b'}
    assert not any(f['rule'] == 'b' and f['subject'] == 'out.txt' for f in findings)


def test_rejected_or_no_effect_write_does_not_exempt_final_path(tmp_path):
    s = Session(tmp_path)
    s.feed(pair())
    ev = output('unread_subject', 'Write')
    assert held(s.send(ev))
    s.send(dict(ev, hook_event_name='PostToolUse', tool_response={'content': 'ok'}))
    assert held(s.send(output('out.txt')))
    assert 'b' in s.rules()
    ev = output('source data', 'Write', tid='no-effect')
    ev['tool_input']['file_path'] = 'other.txt'
    assert not held(s.send(ev))
    s.send(dict(ev, hook_event_name='PostToolUseFailure', tool_response={'content': 'failed'}, makoto={'no_effect': True}))
    assert held(s.send(output('out.txt')))
    assert 'b' in s.rules()


@pytest.mark.parametrize('text,value', [
    ('[source](new/file.txt)', 'new/file.txt'),
    ('(new/file.txt)', 'new/file.txt'),
    ('`call(unread_subject)`', 'unread_subject'),
    ('report-file.txt', 'report-file.txt'),
    ('123abcd', '123abcd'),
    ('a' * 40, 'a' * 40),
    ('v1.2', 'v1.2'),
    ('1.2.3-rc1+build2', '1.2.3-rc1+build2'),
])
def test_name_variants_still_hold(tmp_path, text, value):
    assert value in [s.text for s in names(text)]
    s = Session(tmp_path)
    s.feed(pair())
    assert held(s.send(output(text)))
    assert 'a' in s.rules()
    s.feed(pair(text=text, tid='name'))
    assert not held(s.send(output(text)))


def test_own_quoted_prose_needs_original_reading_not_literal_delimiters(tmp_path):
    s = Session(tmp_path)
    s.send(event('AssistantMessage', content='"exact phrase"'))
    assert held(s.send(output('"exact phrase"')))
    assert s.rules() == {'a'}
    s.feed(pair(text='exact phrase'))
    assert not held(s.send(output('"exact phrase"')))


@pytest.mark.parametrize('path', ['/w/my report.txt', 'my report.txt', './my dir/report.txt'])
def test_quoted_path_with_spaces_is_one_exact_name(tmp_path, path):
    text = '`' + path + '`'
    assert [s.text for s in names(text)] == [path]
    s = Session(tmp_path)
    s.feed(pair())
    assert held(s.send(output(text)))
    assert any(f['rule'] == 'b' and f['subject'] == path for f in s.journal()[-1]['findings'])
    s.feed(pair(text=text, tid='name'))
    assert not held(s.send(output(text)))


@pytest.mark.parametrize('reference', ['my report.txt', '`my report.txt`', '/w/my report.txt', 'Saved my report.txt'])
def test_output_paths_with_spaces_clear_b_and_a(tmp_path, reference):
    s = Session(tmp_path)
    s.feed(pair())
    ev = output('source data', 'Write')
    ev['tool_input']['file_path'] = 'my report.txt'
    assert not held(s.send(ev))
    s.send(dict(ev, hook_event_name='PostToolUse', tool_response={'content': 'ok'}))
    s.feed(pair(ti={'file_path': 'my report.txt'}, text='source data', tid='readback'))
    assert not held(s.send(output(reference)))
