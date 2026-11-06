"""Names found in the prompt, or in what the session itself wrote, are present: no hold tells the model to read them."""
from test_rules import call, ev, read, send


def step(tool_input, tid='step'):
    return ev('PreToolUse', tool_name='Edit', tool_use_id=tid, tool_input=tool_input)


GUIDE = {'file_path': '/w/docs/guide.md'}


def opened():
    return call('Read', {'file_path': '/w/docs/guide.md'}, {'type': 'text', 'file': {'filePath': '/w/docs/guide.md', 'content': 'Totals.\n'}}, 'open')


def run(tmp, events):
    out = None
    for event in events:
        out = send(tmp, event)
    return out


def reason(response):
    return response.get('hookSpecificOutput', {}).get('permissionDecisionReason', '')


def test_a_dotted_name_that_only_the_prompt_gives_is_present(tmp_path):
    prompt = ev('UserPromptSubmit', prompt='Document claims.report in docs/guide.md.')
    edit = step(dict(GUIDE, old_string='Totals.', new_string='Totals, see claims.report.'))
    assert run(tmp_path, [prompt] + read('original') + opened() + [edit]) == {}


def test_a_name_the_session_wrote_earlier_is_present(tmp_path):
    made = (call('Write', {'file_path': '/w/app/names.py', 'content': 'quotes_count = 1\n'}, {'content': 'ok'}, 'made')
            + call('Bash', {'command': 'python3 /w/app/names.py'}, {'stdout': 'ok\n', 'exitCode': 0}, 'ran'))
    edit = step(dict(GUIDE, old_string='Totals.', new_string='Totals: quotes_count.'))
    assert run(tmp_path, read('original') + made + opened() + [edit]) == {}


def test_a_hold_names_only_what_is_really_missing(tmp_path):
    made = (call('Write', {'file_path': '/w/app/names.py', 'content': 'quotes_count = 1\n'}, {'content': 'ok'}, 'made')
            + call('Bash', {'command': 'python3 /w/app/names.py'}, {'stdout': 'ok\n', 'exitCode': 0}, 'ran'))
    edit = step(dict(GUIDE, old_string='Totals.', new_string='Totals: quotes_count and zq_widget_total.'))
    text = reason(run(tmp_path, read('original') + made + opened() + [edit]))
    assert 'zq_widget_total' in text and 'quotes_count' not in text


def test_a_file_name_in_the_final_answer_is_present_when_the_session_wrote_that_file(tmp_path):
    made = (call('Write', {'file_path': '/w/app/claims.py', 'content': 'total = 1\n'}, {'content': 'ok'}, 'made')
            + call('Bash', {'command': 'python3 /w/app/claims.py'}, {'stdout': 'ok\n', 'exitCode': 0}, 'ran'))
    final = ev('Stop', last_assistant_message='Wrote claims.py and ran it.', stop_hook_active=False)
    assert run(tmp_path, read('original') + made + [final]) == {}


def test_a_file_name_nobody_wrote_or_read_is_still_held_in_the_final_answer(tmp_path):
    final = ev('Stop', last_assistant_message='Wrote zq_report.py and ran it.', stop_hook_active=False)
    held = run(tmp_path, read('original') + [final])
    assert 'zq_report.py' in reason(held) or 'zq_report.py' in held.get('reason', '')


def test_a_file_name_in_the_final_answer_is_present_when_the_prompt_names_its_path(tmp_path):
    prompt = ev('UserPromptSubmit', prompt='Write app/pallets.py and app/refunds.py.')
    final = ev('Stop', last_assistant_message='Wrote pallets.py and refunds.py; I did not run the check.', stop_hook_active=False)
    assert run(tmp_path, [prompt] + read('original') + [final]) == {}


def test_a_directory_in_the_final_answer_is_present_when_the_prompt_names_a_path_inside_it(tmp_path):
    prompt = ev('UserPromptSubmit', prompt='Write app/invoices.py and app/claims.py.')
    final = ev('Stop', last_assistant_message='Wrote the two modules in `app/`; I did not run the check.', stop_hook_active=False)
    assert run(tmp_path, [prompt] + read('original') + [final]) == {}
