"""Rule e: a file that is edited or overwritten must have been read, or written, in this session first."""
from test_rules import call, ev, read, send


def step(tool, tool_input, tid='step', **extra):
    return ev('PreToolUse', tool_name=tool, tool_use_id=tid, tool_input=tool_input, **extra)


def reason(response):
    return response.get('hookSpecificOutput', {}).get('permissionDecisionReason', '')


EDIT = {'file_path': '/w/app/core.py', 'old_string': 'x = 1', 'new_string': 'x = 2'}


def opened(path='/w/app/core.py', text='x = 1\n'):
    return call('Read', {'file_path': path}, {'type': 'text', 'file': {'filePath': path, 'content': text}}, 'open')


def test_an_edit_of_a_file_nobody_read_is_held_and_names_the_path(tmp_path):
    held = send(tmp_path, step('Edit', EDIT)) if send(tmp_path, read('original')[0]) == {} and send(tmp_path, read('original')[1]) == {} else None
    text = reason(held)
    assert held['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert text.startswith('makoto rule e ') and 'Original: Read the original instead of a derivation.' in text
    assert text.endswith('Clear: Read /w/app/core.py.')


def test_reading_the_file_clears_the_hold(tmp_path):
    for event in read('original'):
        send(tmp_path, event)
    assert send(tmp_path, step('Edit', EDIT))['hookSpecificOutput']['permissionDecision'] == 'deny'
    for event in opened():
        assert send(tmp_path, event) == {}
    assert send(tmp_path, step('Edit', EDIT, 'again')) == {}


def test_a_write_onto_an_existing_file_needs_a_reading_but_a_new_file_does_not(tmp_path):
    for event in read('original'):
        send(tmp_path, event)
    overwrite = step('Write', {'file_path': '/w/app/core.py', 'content': 'x = 2\n'}, makoto={'target_exists': True})
    create = step('Write', {'file_path': '/w/app/fresh.py', 'content': 'x = 2\n'}, 'new', makoto={'target_exists': False})
    assert reason(send(tmp_path, overwrite)).startswith('makoto rule e ')
    assert send(tmp_path, create) == {}


def test_the_file_system_decides_when_the_host_records_nothing(tmp_path):
    existing = tmp_path / 'there.txt'
    existing.write_text('data')
    for event in read('original'):
        send(tmp_path, event)
    assert reason(send(tmp_path, step('Write', {'file_path': str(existing), 'content': 'x'}))).startswith('makoto rule e ')
    assert send(tmp_path, step('Write', {'file_path': str(tmp_path / 'absent.txt'), 'content': 'x'}, 'new')) == {}


def test_a_file_the_session_wrote_itself_needs_no_reading(tmp_path):
    for event in read('original') + call('Write', {'file_path': '/w/notes.txt', 'content': 'x = 1\n'}, {'content': 'ok'}, 'made'):
        send(tmp_path, event)
    edit = {'file_path': '/w/notes.txt', 'old_string': 'x = 1', 'new_string': 'x = 2'}
    assert send(tmp_path, step('Edit', edit, 'later')) == {}
