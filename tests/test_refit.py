"""D4, D7–D8, D11 and D16–D18 refit discriminators."""
import pytest
from test_shapes import event, pair, output
from makoto2.provenance import Ledger
from makoto2.evaluate import evaluate


def feed(ledger, rows):
    for row in rows:
        ledger.ingest(row)


def rules(ledger, text, boundary='Stop'):
    return {f['rule'] for f in evaluate(ledger, output(text, boundary))[0]}


@pytest.mark.parametrize('failure', ['event', 'exit_code', 'exitCode', 'exit', 'isError', 'is_error'])
def test_unsuccessful_result_has_no_reading(failure):
    ledger = Ledger()
    rows = pair(text='source_id')
    if failure == 'event':
        rows[1]['hook_event_name'] = 'PostToolUseFailure'
    else:
        rows[1]['tool_response'][failure] = True if failure.startswith('is') else 1
    feed(ledger, rows)
    assert not ledger.readings and not ledger.point_readings
    assert rules(ledger, 'source_id') == {'a', 'b'}


@pytest.mark.parametrize('tool', ['Task', 'Agent'])
def test_worker_response_never_pays_reading_or_execution(tool):
    ledger = Ledger()
    feed(ledger, pair(tool, {}, 'source_id', makoto={'reads': [{'subject': 'worker.py'}], 'invocation': {'subject': 'worker.py'}}))
    assert not ledger.readings and not ledger.executions and not ledger.point_readings
    assert 'source_id' in ledger.own


@pytest.mark.parametrize('tool', ['Read', 'Bash', 'Grep', 'Glob', 'WebFetch', 'WebSearch', 'mcp__source__read'])
def test_any_successful_tool_can_read_identifier(tool):
    ledger = Ledger()
    feed(ledger, pair(tool, {}, 'source_id'))
    assert rules(ledger, 'source_id') == set()


@pytest.mark.parametrize('exit_code', [0, 1, 126, 127])
def test_unexecuted_status_is_not_a_run(exit_code):
    ledger = Ledger()
    rows = pair('Run', {'file_path': 'worker.py'}, 'response')
    rows[1]['tool_response']['exit_code'] = exit_code
    feed(ledger, rows)
    assert bool(ledger.executions) == (exit_code not in (126, 127))


@pytest.mark.parametrize('boundary', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'commit', 'Stop'])
@pytest.mark.parametrize('body', ['# source_id returns 731\nnew_value = 2', 'new_value = "source_id returns 731"', '{"note": "source_id is recorded as 731"}'])
def test_facts_inside_programs_are_claims(boundary, body):
    assert rules(Ledger(), body, boundary) >= {'a', 'b'}


def test_search_returned_url_is_read_but_query_is_not():
    ledger = Ledger()
    url = 'https://source.test/item'
    feed(ledger, pair('WebSearch', {'query': url}, 'nothing'))
    assert rules(ledger, url) == {'a', 'b'}
    feed(ledger, pair('WebSearch', {'query': 'find it'}, url, tid='found'))
    assert rules(ledger, url) == set()


@pytest.mark.parametrize('tool', ['Run', 'mcp__runner__execute'])
def test_run_at_claimed_point_pays_other_point(tool):
    ledger = Ledger()
    feed(ledger, pair(ti={'file_path': 'worker.py'}, text='old', makoto={'place': {'host': 'old'}}))
    rows = pair(tool, {'file_path': 'worker.py'}, 'response', tid='run', makoto={'place': {'host': 'new'}, 'invocation': {'subject': 'worker.py'}})
    feed(ledger, rows)
    assert 'c' not in rules(ledger, 'worker.py host=new')
    assert 'c' in rules(ledger, 'worker.py host=elsewhere')


@pytest.mark.parametrize('text,selected', [('worker.py accepts 731', False), ('worker.py is recorded as 731', False), ('worker.py returns 731', True)])
def test_only_behavior_selects_unchanged_code(text, selected):
    ledger = Ledger()
    feed(ledger, pair(ti={'file_path': 'worker.py'}, text='def worker(): return 731'))
    assert ('d' in rules(ledger, text)) == selected


def test_search_result_pays_the_returned_url_point():
    ledger = Ledger()
    url = 'https://source.test/item'
    feed(ledger, pair('WebFetch', {'url': 'https://other.test/item'}, url))
    assert 'c' in rules(ledger, url)
    feed(ledger, pair('WebSearch', {'query': 'find it'}, url, tid='search'))
    assert rules(ledger, url) == set()


def test_behavior_output_identifier_is_not_an_executed_subject():
    ledger = Ledger()
    feed(ledger, pair(ti={'file_path': 'worker.py'}, text='result_id'))
    feed(ledger, pair('Run', {'file_path': 'worker.py'}, 'result_id', tid='run'))
    assert rules(ledger, 'worker.py returns result_id') == set()


def test_unread_behavior_subject_needs_run():
    assert rules(Ledger(), 'worker.py returns a response') == {'a', 'b', 'd'}


@pytest.mark.parametrize('body', ['print(731)', 'new_value = 731 # The source_id is recorded', '{"new_key": 731}'])
def test_only_introduced_values_are_creations(body):
    findings = evaluate(Ledger(), output(body, 'Write'))[0]
    assert not any(f['subject'] == '731' for f in findings)


@pytest.mark.parametrize('key', ['record_uri', 'document_url', 'resource_path', 'uri'])
def test_generic_location_input_needs_successful_matched_result(key):
    ledger = Ledger()
    uri = 'mcp://archive/objects/23'
    rows = pair('mcp__archive__fetch', {key: uri}, 'value', tid='location')
    ledger.ingest(rows[0])
    assert 'b' in rules(ledger, uri)
    ledger.ingest(rows[1])
    assert rules(ledger, uri) == set()
    assert 'b' in rules(ledger, 'mcp://archive/objects/24')


@pytest.mark.parametrize('response,executed', [
    ({'content': 'opaque failure', 'isError': True}, False),
    ({'content': 'opaque failure', 'error': 'transport'}, False),
    ({'stderr': 'program failure', 'exit_code': 1}, True),
    ({'content': 'Runner connection failed before process creation'}, True),
])
def test_run_failure_uses_structured_status_only(response, executed):
    ledger = Ledger()
    rows = pair('mcp__runner__execute', {'program_path': './worker.py', 'argv': ['7']}, tid='run')
    rows[1]['tool_response'] = response
    feed(ledger, rows)
    assert bool(ledger.executions) == executed


@pytest.mark.parametrize('path', ['/tmp/object.txt', r'C:\Some Place\object.txt'])
def test_inline_python_mutation_requires_a_later_read(path):
    import shlex
    ledger = Ledger()
    feed(ledger, pair(ti={'file_path': path}, text='before'))
    script = f'import pathlib as fs; p=fs.Path({path!r}); p.write_text("after")'
    feed(ledger, pair('Bash', {'command': 'python3 -c ' + shlex.quote(script)}, '', tid='mutate'))
    assert rules(ledger, path) == {'c'}
    feed(ledger, pair(ti={'file_path': path}, text='after', tid='reread'))
    assert rules(ledger, path) == set()


def test_inline_python_unselected_write_does_not_mutate():
    import shlex
    ledger = Ledger()
    feed(ledger, pair(ti={'file_path': '/tmp/object.txt'}, text='before'))
    script = 'from pathlib import Path\nif False:\n    Path("/tmp/object.txt").write_text("after")'
    feed(ledger, pair('Bash', {'command': 'python3 -c ' + shlex.quote(script)}, '', tid='conditional'))
    assert not ledger.mutations


def test_acceptance_value_with_work_noun_is_not_behavior():
    ledger = Ledger()
    text = 'maintenance order accepts code word work order-56'
    feed(ledger, pair(text=text))
    assert rules(ledger, text, 'commit') == set()


def test_mcp_run_response_is_distinct_from_session_written_program():
    ledger = Ledger()
    feed(ledger, pair('Write', {'file_path': './worker.py', 'content': 'print(731)'}, tid='write'))
    feed(ledger, pair('mcp__runner__execute', {'program_path': './worker.py', 'argv': []}, 'result_id', tid='run'))
    assert rules(ledger, './worker.py returns result_id') == set()
