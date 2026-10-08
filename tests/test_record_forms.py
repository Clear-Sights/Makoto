"""Independent plants for source existence, denied mutations and fetch forms."""
import pytest

from test_shapes import Session, event, pair, output
from makoto2.precision import extract, names, package_parts
from run_pairs import held


@pytest.mark.parametrize('tool,ti,source', [
    ('Read', {'file_path': 'raw.txt'}, 'left 27 right 18'),
    ('Bash', {'command': 'probe'}, 'left 27 right 18'),
    ('Grep', {'path': 'raw.txt', 'pattern': 'left'}, 'left 27'),
    ('Glob', {'pattern': '*.txt'}, 'raw.txt'),
    ('Query', {'query': 'select amount'}, '27'),
])
@pytest.mark.parametrize('earlier', [False, True])
def test_repeated_derived_prose_only_needs_original_reading(tmp_path, tool, ti, source, earlier):
    s = Session(tmp_path)
    text = 'The difference equals nine.'
    if earlier:
        s.feed(pair(tool, ti, source))
    s.send(event('AssistantMessage', content=text))
    s.send(event('UserPromptSubmit', prompt='Explain again'))
    if not earlier:
        assert held(s.send(output(text)))
        s.feed(pair(tool, ti, source))
    assert not held(s.send(output(text)))
    assert s.rules() == set()


@pytest.mark.parametrize('tool,ti', [('Read', {'file_path': 'draft.txt'}), ('Bash', {'command': 'cat draft.txt'})])
@pytest.mark.parametrize('confirmed', [False, True])
@pytest.mark.parametrize('post_input', [False, True])
def test_denied_writer_never_creates_evidence_and_reported_mutation_taints(tmp_path, tool, ti, confirmed, post_input):
    s = Session(tmp_path)
    s.send(event('UserPromptSubmit', prompt='draft.txt'))
    write = output('The difference equals nine.', 'Write')
    write['tool_input']['file_path'] = 'draft.txt'
    assert held(s.send(write))
    if confirmed:
        post = dict(write, hook_event_name='PostToolUse', tool_response='Created file')
        if not post_input:
            del post['tool_input']
        s.send(post)
    s.feed(pair(tool, ti, 'The difference equals nine.', tid='readback'))
    assert held(s.send(output('The difference equals nine.'))) == confirmed
    if confirmed:
        assert s.rules() == {'a'}
        s.feed(pair(ti={'file_path': 'raw.txt'}, text='left 27 right 18', tid='original'))
        assert not held(s.send(output('The difference equals nine.')))


@pytest.mark.parametrize('suffix', ['.', ',', ';', ')', '`'])
def test_version_pair_does_not_include_sentence_punctuation(tmp_path, suffix):
    value = 'quivora 17.24.6'
    text = value + suffix
    assert value in [span.text for span in extract(text)]
    assert value + '.' not in [span.text for span in extract(text)]
    s = Session(tmp_path)
    s.send(event('Register', makoto={'external_subjects': [value]}))
    s.feed(pair(text=value))
    assert held(s.send(output(text))) and s.rules() == {'c'}
    s.feed(pair('WebFetch', {'url': 'https://packages.example.test/q'}, value, tid='fetch'))
    assert not held(s.send(output(text)))


@pytest.mark.parametrize('version', ['17.24.6rc4', '17.24.6.post4', '17.24.6-rc4+build8'])
def test_version_suffixes_keep_exact_characters(version):
    value = 'quivora==' + version
    assert package_parts(value) == ('quivora', version)
    assert value in [span.text for span in extract(value + '.')]


@pytest.mark.parametrize('value', ['7.25 mA', '8.75 Hz', '4.25 µs'])
def test_prose_before_decimal_unit_does_not_name_external_package(tmp_path, value):
    text = 'The observed quantity equals ' + value + '.'
    assert not [span for span in extract(text) if span.kind == 'external-package']
    s = Session(tmp_path)
    s.feed(pair(text=value))
    assert not held(s.send(output(text)))


def test_explicit_package_operator_is_not_hidden_by_adjacent_unit(tmp_path):
    text = 'quivora@7.25 mA'
    s = Session(tmp_path)
    s.feed(pair(text=text))
    assert held(s.send(output(text))) and s.rules() == {'c'}


def test_unit_match_inside_version_does_not_hide_package():
    assert 'quivora 17.24.6' in [span.text for span in extract('quivora 17.24.6 released')]


@pytest.mark.parametrize('response', ['page bytes', {'stdout': 'page bytes'}, {'stdout': 'page bytes', 'exitCode': 0}])
def test_native_fetch_without_exit_field_is_completed_reading(tmp_path, response):
    s = Session(tmp_path)
    url = 'https://proof.example.test/checked'
    s.feed(pair(text=url))
    call = pair('Bash', {'command': 'curl -fsSL ' + url}, tid='fetch')
    call[1]['tool_response'] = response
    s.feed(call)
    assert not held(s.send(output(url)))


@pytest.mark.parametrize('variant', ['failed', 'pending', 'unpaired', 'wrong_subject', 'background'])
def test_missing_or_failed_network_receipt_still_holds(tmp_path, variant):
    s = Session(tmp_path)
    url = 'https://proof.example.test/checked'
    s.feed(pair(text=url))
    call = pair('Bash', {'command': 'curl -fsSL ' + url}, tid='fetch')
    call[1]['tool_response'] = {'stdout': 'page bytes'}
    if variant == 'failed':
        call[1]['tool_response']['exit_code'] = 7
    elif variant == 'pending':
        call = call[:1]
    elif variant == 'unpaired':
        call = call[1:]
    elif variant == 'wrong_subject':
        call[0]['tool_input']['command'] = 'curl https://proof.example.test/other'
    elif variant == 'background':
        call[1]['tool_response']['backgroundTaskId'] = 'job'
    s.feed(call)
    assert held(s.send(output(url))) and s.rules() == {'c'}


@pytest.mark.parametrize('form', ['quivora@17.24.6', 'quivora==17.24.6', 'quivora version 17.24.6', 'quivora v17.24.6'])
def test_package_subject_is_same_exact_name_and_release_across_separators(tmp_path, form):
    assert package_parts(form) == ('quivora', '17.24.6')
    s = Session(tmp_path)
    s.send(event('Register', makoto={'external_subjects': ['quivora 17.24.6']}))
    s.feed(pair(text='quivora 17.24.6'))
    s.feed(pair('WebFetch', {'url': 'https://proof.example.test/pkg'}, form, tid='fetch'))
    assert not held(s.send(output('quivora 17.24.6')))


@pytest.mark.parametrize('other', ['quivora 17.24.5', 'quivoraExtra 17.24.6', 'Quivora 17.24.6'])
def test_package_identity_keeps_exact_name_and_version(tmp_path, other):
    s = Session(tmp_path)
    s.send(event('Register', makoto={'external_subjects': ['quivora 17.24.6']}))
    s.feed(pair(text='quivora 17.24.6'))
    s.feed(pair('WebFetch', {'url': 'https://proof.example.test/pkg'}, other, tid='fetch'))
    assert held(s.send(output('quivora 17.24.6'))) and s.rules() == {'c'}


@pytest.mark.parametrize('subject', ['17.24.6', 'Archivora', 'archivora_id', 'archivora.module', 'reader@proof.example.test'])
def test_nonexternal_name_forms_do_not_require_network(tmp_path, subject):
    s = Session(tmp_path)
    s.feed(pair(text=subject))
    assert not held(s.send(output(subject)))
    # Bare local and public names have the same form. Host classification pays
    # the ambiguity without adding a public-name dictionary to the checker.
    s.send(event('Register', makoto={'external_subjects': [subject]}))
    assert held(s.send(output(subject))) and s.rules() == {'c'}
