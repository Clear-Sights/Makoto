"""Rule b takes a name from text next to punctuation. Each of the five corpus false positives, reproduced."""
import pytest

from test_rules import call, ev, read, send

STYLE_PROMPT = ('Functions named report_* return a dict whose keys all start with rep_. Functions named summarize_* '
                'return a dict whose keys all start with the module name and an underscore, for example {name}.')
STYLE_DOC = ('# Style\n\n- Four spaces, no tabs.\n- Functions named report_* return a dict whose keys all start with rep_.\n'
             '- Functions named summarize_* return a dict whose keys all start with the module name and an underscore, '
             'for example {name}.\n')


def run(tmp, events):
    """Send every event; return the answer to the last one."""
    out = None
    for event in events:
        out = send(tmp, event)
    return out


def writer(tool, tool_input, tid='step'):
    return ev('PreToolUse', tool_name=tool, tool_use_id=tid, tool_input=tool_input)


def test_a_method_call_on_an_expression_is_not_a_hidden_file(tmp_path):
    # corpus d32499a1 #13 and 22784a89 #23: `.quantize` in a new function body
    code = 'from decimal import Decimal, ROUND_HALF_EVEN\n\n\ndef cents(x):\n    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))\n'
    prompt = ev('UserPromptSubmit', prompt='In app/money.py make cents(x) return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)).')
    step = writer('Write', {'file_path': 'app/money.py', 'content': code})
    assert run(tmp_path, [prompt] + read('original') + [step]) == {}


@pytest.mark.parametrize('name', ['invoices_count', 'claims_count'])
def test_a_name_before_a_sentence_ending_period_is_the_name(tmp_path, name):
    # corpus d32499a1 #35 and 22784a89 #25: `rep_.` and `invoices_count.` at the end of a sentence in the prompt
    prompt = ev('UserPromptSubmit', prompt=STYLE_PROMPT.format(name=name))
    step = writer('Write', {'file_path': 'docs/dev/style.md', 'content': STYLE_DOC.format(name=name)})
    assert run(tmp_path, [prompt] + read('original') + [step]) == {}


def test_a_dotted_name_the_session_already_wrote_is_produced_not_unread(tmp_path):
    # corpus cf29e150 #45: the session wrote `app.core.depth_value` in an earlier edit (#39), then used it again
    first = call('Write', {'file_path': '/w/app/uses.py', 'content': 'import app.core\n\nvalue = app.core.depth_value(1)\n'},
                 {'content': 'ok'}, 'w1')
    source = 'import app.core\n\ndef notify_over(x, limit):\n    return app.core.depth(x) > limit\n'
    opened = call('Read', {'file_path': '/w/app/notify.py'}, {'type': 'text', 'file': {'filePath': '/w/app/notify.py', 'content': source}}, 'r1')
    step = writer('Edit', {'file_path': '/w/app/notify.py', 'old_string': '    return app.core.depth(x) > limit',
                           'new_string': '    return app.core.depth_value(x) > limit'})
    assert run(tmp_path, read('original') + first + opened + [step]) == {}


def test_a_dotted_name_nobody_wrote_or_read_is_still_held(tmp_path):
    # corpus cf29e150 #39, the first use: the name is nowhere yet, so the hold stands
    source = 'import app.core\n\ndef notify_over(x, limit):\n    return app.core.depth(x) > limit\n'
    opened = call('Read', {'file_path': '/w/app/notify.py'}, {'type': 'text', 'file': {'filePath': '/w/app/notify.py', 'content': source}}, 'r1')
    step = writer('Edit', {'file_path': '/w/app/notify.py', 'old_string': '    return app.core.depth(x) > limit',
                           'new_string': '    return app.core.depth_value(x) > limit'})
    held = run(tmp_path, opened + [step])
    assert held['hookSpecificOutput']['permissionDecision'] == 'deny' and 'app.core.depth_value' in held['hookSpecificOutput']['permissionDecisionReason']


def test_method_names_nobody_read_are_still_held(tmp_path):
    # `.get(` after a call is not named anywhere, so treating `.name(` as a call must not admit it
    code = 'def merge(a, b):\n    return a.union(b).get(0)\n'
    held = run(tmp_path, read('original') + [writer('Write', {'file_path': 'app/merge.py', 'content': code})])
    reason = held['hookSpecificOutput']['permissionDecisionReason']
    assert held['hookSpecificOutput']['permissionDecision'] == 'deny' and '.get' in reason


def test_a_name_that_only_looks_like_it_is_still_held(tmp_path):
    # The fixes must not turn the check off: a name found nowhere is still held.
    step = writer('Write', {'file_path': 'docs/dev/style.md', 'content': 'Keys start with zq_widget_total.\n'})
    held = run(tmp_path, read('original') + [step])
    assert held['hookSpecificOutput']['permissionDecision'] == 'deny' and 'zq_widget_total' in held['hookSpecificOutput']['permissionDecisionReason']
