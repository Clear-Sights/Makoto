"""Precision extractor, persisted session history and borrowed-store plants."""
import hashlib
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'plugin'), str(ROOT / 'tools')]
from makoto2.precision import extract, contains
from test_shapes import Session, event, pair, output
from run_pairs import held


@pytest.mark.parametrize('text,expected', [
    ('"hello world"', 'hello world'), ("'hello world'", 'hello world'),
    ('“hello world”', 'hello world'), ('‘hello world’', 'hello world'),
    ('`hello world`', 'hello world'), ('```py\na = 1\n```', 'a = 1\n'),
    ('~~~sh\na = 1\n~~~', 'a = 1\n'), ('/w/foo.txt', '/w/foo.txt'),
    ('../foo.txt', '../foo.txt'), ('https://example.test/?x=1', 'https://example.test/?x=1'),
    ('a@b.test', 'a@b.test'), ('id_abc', 'id_abc'), ('camelCase', 'camelCase'),
    ('c86842a', 'c86842a'), ('550e8400-e29b-41d4-a716-446655440000', '550e8400-e29b-41d4-a716-446655440000'),
    ('1.2.3', '1.2.3'), ('2026-10-06T19:24Z', '2026-10-06T19:24Z'),
    ('12 ms', '12 ms'), ('1.5kg', '1.5kg'), ('nonenglishword', 'nonenglishword'),
    ('snake_case', 'snake_case'), ('日本語', '日本語')])
def test_precision_forms_preserve_exact_offsets(text, expected):
    spans = extract(text)
    assert expected in [s.text for s in spans]
    assert all(s.text == text[s.start:s.end] for s in spans)
    assert spans == extract(text)


@pytest.mark.parametrize('text', ['the source is read', 'a statement', 'I have read the data', 'The file is here.'])
def test_common_prose_is_not_precision(text):
    assert extract(text) == []


def test_output_lines_and_boundaries():
    lines = 'Error: read failed\n  at thing (file.py:19)\n'
    assert [s.text for s in extract(lines, tool_output=True) if s.kind == 'output-line'] == lines.splitlines()
    assert contains('value 731 here', '731')
    assert not contains('value 731 here', '73')
    assert not contains('prefix_data_91', 'data_91')


@pytest.mark.parametrize('format', ['native', 'messages'])
def test_transcript_includes_earlier_turns_and_excludes_assistant(tmp_path, format):
    s = Session(tmp_path)
    rows = pair(text='original_91') + [event('UserPromptSubmit', prompt='next turn'), event('AssistantMessage', content='invented_92')]
    if format == 'messages':
        rows = [
            {'type': 'assistant', 'sessionId': 'plant', 'message': {'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'read', 'name': 'Read', 'input': {'file_path': 'source.txt'}}]}},
            {'type': 'user', 'sessionId': 'plant', 'message': {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'read', 'content': 'original_91'}]}},
            {'type': 'user', 'sessionId': 'plant', 'message': {'role': 'user', 'content': 'next turn'}},
            {'type': 'assistant', 'sessionId': 'plant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'invented_92'}]}}]
    transcript = tmp_path / 'transcript.jsonl'
    transcript.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    assert not held(s.send(dict(output('original_91'), transcript_path=str(transcript))))
    assert held(s.send(dict(output('invented_92'), transcript_path=str(transcript))))
    assert 'b' in s.rules()


def test_transcript_prior_write_invalidates_old_read(tmp_path):
    s = Session(tmp_path)
    write = event('PreToolUse', tool_name='Write', tool_use_id='old-write', tool_input={'file_path': 'source.txt', 'content': 'original_91'})
    rows = pair(text='original_91') + [write, dict(write, hook_event_name='PostToolUse', tool_response={'content': 'ok'})] + pair(text='original_91', tid='own-read')
    transcript = tmp_path / 'transcript.jsonl'
    transcript.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    assert held(s.send(dict(output('original_91'), transcript_path=str(transcript))))
    assert {'a', 'b'} <= s.rules()


def test_transcript_import_cannot_overrule_denial(tmp_path):
    s = Session(tmp_path)
    write = output('data_91', 'Write')
    assert held(s.send(write))
    rows = [write, dict(write, hook_event_name='PostToolUse', tool_response={'content': 'data_91'})]
    transcript = tmp_path / 'transcript.jsonl'
    transcript.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    assert held(s.send(dict(output('data_91'), transcript_path=str(transcript))))


@pytest.mark.parametrize('variant', ['valid', 'bad_hash', 'unreferenced', 'short_address'])
def test_detio_store_only_witnessed_verified_bytes(tmp_path, variant):
    s = Session(tmp_path)
    store = tmp_path / 'store'
    objects = store / 'objects'
    objects.mkdir(parents=True)
    data = b'stored_value_91'
    address = hashlib.sha256(data).hexdigest()
    if variant == 'short_address':
        address = address[:12]
    (objects / address).write_bytes(b'invented_value_92' if variant == 'bad_hash' else data)
    text = 'source data' if variant == 'unreferenced' else 'detio://' + address
    s.feed(pair(text=text, makoto={'detio_store': str(store)})) if variant != 'bad_hash' else [s.send(e) for e in pair(text=text, makoto={'detio_store': str(store)})]
    response = s.send(output('stored_value_91'))
    assert held(response) == (variant in ('bad_hash', 'unreferenced'))


def test_host_current_turn_metadata_does_not_import_candidate_receipts(tmp_path):
    s = Session(tmp_path)
    s.feed(pair('WebFetch', {'url': 'https://example.test/a'}, 'data_91'))
    ev = output('https://example.test/a')
    ev['makoto'] = {'turn_id': 'next', 'reads': [{'subject': 'invented', 'content': 'paid_93'}]}
    assert held(s.send(ev))
    assert s.rules() == {'c'}


@pytest.mark.parametrize('text', ['$HOME', 'a*b', 'foo[0]', 'foo()', "don't", 'widget v1.2.3', 'widget version 1.2.3'])
def test_mixed_symbol_and_version_forms(text):
    assert text in [s.text for s in extract(text)]


def test_detio_invalid_object_fails_closed_and_can_be_repaired(tmp_path):
    s = Session(tmp_path)
    store = tmp_path / 'store'
    (store / 'objects').mkdir(parents=True)
    data = b'stored_value_91'
    address = hashlib.sha256(data).hexdigest()
    obj = store / 'objects' / address
    obj.write_bytes(b'wrong bytes')
    call = pair(text='detio://' + address, makoto={'detio_store': str(store)})
    assert not held(s.send(call[0]))
    assert held(s.send(call[1]))
    assert held(s.send(output('stored_value_91')))
    obj.write_bytes(data)
    assert not held(s.send(call[1]))
    assert not held(s.send(output('stored_value_91')))


def test_transcript_current_candidate_cannot_import_future_read(tmp_path):
    s = Session(tmp_path)
    candidate = output('invented_91', 'Write')
    rows = [candidate] + pair(text='invented_91')
    transcript = tmp_path / 'transcript.jsonl'
    transcript.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    assert held(s.send(dict(candidate, transcript_path=str(transcript))))
    assert 'a' in s.rules()


def test_transcript_cross_session_is_transport_failure(tmp_path):
    s = Session(tmp_path)
    transcript = tmp_path / 'transcript.jsonl'
    transcript.write_text(json.dumps(dict(pair()[0], session_id='other'))+'\n')
    response = s.send(dict(output(), transcript_path=str(transcript)))
    assert held(response)
    assert 'session identity mismatch' in response['reason']


def test_repeated_identical_prompt_is_a_new_online_turn(tmp_path):
    s = Session(tmp_path)
    prompt = event('UserPromptSubmit', prompt='same words')
    rows = [prompt] + pair('WebFetch', {'url': 'https://example.test/a'}, 'data_91') + [prompt]
    transcript = tmp_path / 'transcript.jsonl'
    transcript.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    assert held(s.send(dict(output('https://example.test/a'), transcript_path=str(transcript))))
    assert s.rules() == {'c'}


@pytest.mark.parametrize('text', ['alpha–beta', '⛄abc', 'foo^bar'])
def test_symbol_tokens_are_not_lost(text):
    assert text in [s.text for s in extract(text)]


def test_markdown_url_still_requires_online_read(tmp_path):
    s = Session(tmp_path)
    text = '[source](https://example.test/a)'
    s.feed(pair(text=text))
    assert held(s.send(output(text)))
    assert s.rules() == {'c'}
    s.feed(pair('WebFetch', {'url': 'https://example.test/a'}, text, tid='web'))
    assert not held(s.send(output(text)))
