"""Independent ordered-call plants; no spent-set subjects or answer vocabulary."""
import pytest

from test_shapes import Session, event, pair, output
from test_switch import feed, edit, switch_holds
from makoto2.evaluate import evaluate
from makoto2.provenance import Ledger
from makoto2.shell import ordered_segments
from makoto2.precision import names, contains
from run_pairs import held


def call(ledger, command, text='observed result', tid='compound', **response):
    events = pair('Bash', {'command': command}, text, tid=tid)
    events[1]['tool_response'].update(response)
    feed(ledger, events)
    return events


@pytest.mark.parametrize('separator', [';', '&&', '|', '\n'])
@pytest.mark.parametrize('mutation', [
    "sed -i 's/old/new/' loom.py", 'tee loom.py',
    "printf 'new' > loom.py", "printf 'new' >> loom.py",
    'cp template.py loom.py', 'mv template.py loom.py',
])
@pytest.mark.parametrize('reverse', [False, True])
def test_mutation_and_run_order(separator, mutation, reverse):
    ledger = Ledger()
    segments = [mutation, 'python3 loom.py']
    if reverse:
        segments.reverse()
    call(ledger, (' ' + separator + ' ').join(segments))
    assert bool(switch_holds(ledger)) == reverse
    if not reverse:
        _, snapshot = evaluate(ledger, output('Done'))
        assert any(item.get('trace') == ['compound'] and item.get('instruments') == 'makoto2.switch/execution-v1' for item in snapshot)


@pytest.mark.parametrize('runner', ['python3 loom.py', './loom.py', 'pytest loom.py', 'python3 -m pytest loom.py', 'python3 -m loom'])
def test_each_execution_position_after_shell_edit(runner):
    ledger = Ledger()
    call(ledger, "sed -i 's/old/new/' loom.py; " + runner)
    assert not switch_holds(ledger)


@pytest.mark.parametrize('reader', ['cat', 'head', 'tail', 'less', 'more'])
@pytest.mark.parametrize('reverse', [False, True])
def test_original_reader_before_edit_is_lineage(reader, reverse):
    ledger = Ledger()
    segments = [reader + ' loom.py', "sed -i 's/old/new/' loom.py"]
    if reverse:
        segments.reverse()
    call(ledger, '; '.join(segments), 'original_mark changed_mark')
    findings, _ = evaluate(ledger, output('Done'))
    assert ('a' in {f['rule'] for f in findings}) == reverse
    assert switch_holds(ledger)
    # Original-read existence does not make now-stale aggregate bytes fresh.
    assert not ledger.witnesses('original_mark', 'identifier')


def test_multiple_reader_operands_and_prior_own_file():
    ledger = Ledger()
    feed(ledger, edit('own.md'))
    call(ledger, "cat own.md loom.py; sed -i 's/old/new/' loom.py; ruby loom.py")
    assert ledger.source_readings()
    assert not switch_holds(ledger)


@pytest.mark.parametrize('reverse', [False, True])
def test_readback_after_data_edit_and_reversed_order(reverse):
    ledger = Ledger()
    segments = ["sed -i 's/old/new/' loom.toml", 'cat loom.toml']
    if reverse:
        segments.reverse()
    call(ledger, '; '.join(segments))
    assert bool(switch_holds(ledger)) == reverse


@pytest.mark.parametrize('command,paid', [
    ('false && python3 loom.py', False), ('true || python3 loom.py', False),
    ('false || python3 loom.py', True), ('true && python3 loom.py', True),
    ('opaque || python3 loom.py', False),
    ('if test -f loom.py; then python3 loom.py; fi', False),
    ('echo $(python3 loom.py); echo done', False),
    ('echo `python3 loom.py`; echo done', False),
    ('(python3 loom.py); echo done', False),
    ('python3 loom.py & echo done', False),
])
def test_short_circuit_and_opaque_calls(command, paid):
    ledger = Ledger()
    feed(ledger, edit('loom.py'))
    call(ledger, command)
    assert bool(switch_holds(ledger)) != paid


@pytest.mark.parametrize('command,expected', [
    ('echo "a;b && c||d|e\nf"; python3 loom.py', ['echo "a;b && c||d|e\nf"', 'python3 loom.py']),
    ("echo 'a;b|c'; python3 loom.py", ["echo 'a;b|c'", 'python3 loom.py']),
    ('echo a\\;b; python3 loom.py', ['echo a\\;b', 'python3 loom.py']),
    ('echo $(printf "x;y"; echo z); python3 loom.py', ['echo $(printf "x;y"; echo z)', 'python3 loom.py']),
    ('echo "$(printf x; echo y)"; python3 loom.py', ['echo "$(printf x; echo y)"', 'python3 loom.py']),
    ('echo ${value:-x;y}; python3 loom.py', ['echo ${value:-x;y}', 'python3 loom.py']),
    ('echo x # ; python3 fake.py\npython3 loom.py', ['echo x', 'python3 loom.py']),
    ('cat <<\'END\' > loom.py\nprint("x;y")\npython3 fake.py\nEND\npython3 loom.py', ["cat <<'END' > loom.py", 'python3 loom.py']),
    ('cat <<-END > loom.py\n\tpass\n\tEND\npython3 loom.py', ['cat <<-END > loom.py', 'python3 loom.py']),
])
def test_protected_separators_and_heredoc_bodies(command, expected):
    assert [part for part, _ in ordered_segments(command)] == expected


@pytest.mark.parametrize('command', ['echo "unfinished; python3 loom.py', 'echo $(printf x; python3 loom.py', 'cat <<END\npython3 loom.py', 'for x in one; do python3 loom.py; done'])
def test_uncertain_split_returns_legacy_fallback(command):
    assert ordered_segments(command) is None


def test_heredoc_write_then_run_and_body_is_not_a_run():
    ledger = Ledger()
    call(ledger, "cat <<'END' > loom.py\nprint('fresh')\nEND\npython3 loom.py")
    assert not switch_holds(ledger)
    ledger = Ledger()
    call(ledger, "cat <<'END' > loom.py\npython3 loom.py\nEND\necho done")
    assert switch_holds(ledger)


def test_later_edit_unpays_an_earlier_run_inside_one_call():
    ledger = Ledger()
    call(ledger, "sed -i 's/old/new/' loom.py; python3 loom.py; sed -i 's/new/newer/' loom.py")
    assert switch_holds(ledger)


@pytest.mark.parametrize('variant', ['missing', 'background', 'pending', 'unpaired', 'mismatch', 'no_effect'])
def test_order_does_not_bypass_pairing_or_response_contract(variant):
    ledger = Ledger()
    feed(ledger, edit('loom.py'))
    events = pair('Bash', {'command': "sed -i 's/old/new/' loom.py; python3 loom.py"}, 'result', tid='compound')
    if variant == 'missing':
        events[1].pop('tool_response')
    elif variant == 'background':
        events[1]['tool_response'] = {'backgroundTaskId': 'job'}
    elif variant == 'pending':
        events = events[:1]
    elif variant == 'unpaired':
        events = events[1:]
    elif variant == 'mismatch':
        events[1]['tool_input'] = {'command': 'python3 other.py'}
    elif variant == 'no_effect':
        events[1]['makoto'] = {'no_effect': True}
    feed(ledger, events)
    assert bool(switch_holds(ledger)) == (variant != 'no_effect')


@pytest.mark.parametrize('boundary', ['Stop', 'Edit'])
def test_native_boundary_uses_completed_ordered_call(tmp_path, boundary):
    s = Session(tmp_path, live=True)
    s.send(event('UserPromptSubmit', prompt='loom.py out.txt'))
    s.feed(pair('Bash', {'command': "cat loom.py; sed -i 's/old/new/' loom.py; python3 loom.py"}, 'old\nnew', tid='compound'))
    assert not held(s.send(output('The result is new.', boundary)))


@pytest.mark.parametrize('value', ['birch_owner', 'birchHandler', 'writer@letters.example', 'spruce-8.3.2'])
def test_assignment_and_record_punctuation_name_boundaries(value):
    assert value in [s.text for s in names('field=' + value)]
    assert contains('field=' + value, value, names(value)[0].kind)
    assert contains(value + ': known', value, names(value)[0].kind) or names(value)[0].kind == 'path'
    assert not contains('prefix' + value, value, names(value)[0].kind)


@pytest.mark.parametrize('value', ['birch_owner', 'birchHandler', 'writer@letters.example', 'spruce-8.3.2'])
def test_unread_assignment_and_version_tag_hold(value):
    ledger = Ledger()
    feed(ledger, pair(text='unrelated source'))
    findings, _ = evaluate(ledger, output('field=' + value))
    assert any(f['rule'] == 'b' and f['subject'] == value for f in findings)
    feed(ledger, pair(text=value, tid='exact'))
    findings, _ = evaluate(ledger, output('field=' + value))
    assert not any(f['rule'] == 'b' for f in findings)


@pytest.mark.parametrize('compiler,source', [('cc', 'loom.c'), ('c++', 'loom.cpp'), ('rustc', 'loom.rs')])
@pytest.mark.parametrize('variant', ['ordered', 'compile_only', 'old_build', 'syntax_only', 'later_edit', 'wrong_product'])
def test_compiler_product_requires_new_build_and_execution(compiler, source, variant):
    ledger = Ledger()
    change = "sed -i 's/old/new/' " + source
    build = f'{compiler} {source} -o loom-bin'
    commands = [change, build, './loom-bin']
    if variant == 'compile_only':
        commands = commands[:2]
    elif variant == 'old_build':
        commands = [build, change, './loom-bin']
    elif variant == 'syntax_only':
        commands = [change, f'{compiler} -fsyntax-only {source}']
    elif variant == 'later_edit':
        commands.append(change)
    elif variant == 'wrong_product':
        commands[-1] = './other-bin'
    call(ledger, '; '.join(commands))
    assert bool(switch_holds(ledger)) == (variant != 'ordered')


def test_compiler_product_survives_separate_calls_and_replacement_invalidates():
    ledger = Ledger()
    call(ledger, "sed -i 's/old/new/' loom.c; cc loom.c -o loom-bin")
    assert switch_holds(ledger)
    call(ledger, './loom-bin', tid='execute')
    assert not switch_holds(ledger)
    call(ledger, "sed -i 's/new/newer/' loom.c; cp other-bin loom-bin; ./loom-bin", tid='replace')
    assert switch_holds(ledger)


@pytest.mark.parametrize('runner,path', [('go run loom.go', 'loom.go'), ('tclsh loom.tcl', 'loom.tcl'), ('Rscript loom.R', 'loom.R'), ('sqlite3 :memory: < loom.sql', 'loom.sql'), ('psql -f loom.sql', 'loom.sql')])
@pytest.mark.parametrize('reverse', [False, True])
def test_additional_native_language_run_positions(runner, path, reverse):
    ledger = Ledger()
    segments = ["sed -i 's/old/new/' " + path, runner]
    if reverse:
        segments.reverse()
    call(ledger, '; '.join(segments))
    assert bool(switch_holds(ledger)) == reverse


@pytest.mark.parametrize('execute', [False, True])
def test_notebook_converter_requires_execute_flag(execute):
    ledger = Ledger()
    feed(ledger, edit('loom.ipynb', 'NotebookEdit'))
    call(ledger, 'jupyter nbconvert --to notebook ' + ('--execute ' if execute else '') + 'loom.ipynb --stdout')
    assert bool(switch_holds(ledger)) != execute


@pytest.mark.parametrize('code,paid', [
    ('from loom import stitch; print(stitch())', True), ('import loom; print(loom.stitch())', True),
    ('print("loom.py")', False), ('if False: import loom', False),
    ('def load():\n import loom', False), ('raise ValueError(); import loom', False),
    ('import other; print("loom.py")', False),
])
def test_inline_python_only_definite_import_position_pays(code, paid):
    import shlex
    ledger = Ledger()
    feed(ledger, edit('loom.py'))
    call(ledger, 'python -c ' + shlex.quote(code))
    assert bool(switch_holds(ledger)) != paid


@pytest.mark.parametrize('command', ["echo '>' loom.py", 'echo ">" loom.py', "echo ';' loom.py", 'echo "sed -i old loom.py; python3 loom.py"'])
def test_quoted_operator_words_are_data(command):
    ledger = Ledger()
    call(ledger, command)
    assert not ledger.changed_code()


def test_markup_tags_and_commit_prose_do_not_become_paths():
    assert names('<strong>18</strong>') == []
    ledger = Ledger()
    feed(ledger, pair(text='maple.log.Reader'))
    findings, _ = evaluate(ledger, event('PreToolUse', tool_name='Bash', tool_input={'command': "git commit -am 'Update maple.log.Reader'"}))
    assert not findings
    assert [s.text for s in names('`my report.txt`')] == ['my report.txt']


@pytest.mark.parametrize('text', ['The value is 9.2.', 'The reducer outputs 9.2.', 'The internal revision is 9.2.7.', 'The private schema uses revision 9.2.7.'])
def test_decimal_prose_and_version_labels_do_not_name_packages(text):
    from makoto2.precision import extract
    assert not [s for s in extract(text) if s.kind == 'external-package']
    assert [s.text for s in names('Sapling 9.2')] == ['Sapling 9.2']


def test_host_execution_witness_for_opaque_dependency_still_pays():
    ledger = Ledger()
    feed(ledger, edit('loom.py'))
    events = pair('Bash', {'command': 'node opaque-wrapper.js'}, 'result')
    events[1]['makoto'] = {'invocation': {'subject': 'loom.py'}}
    feed(ledger, events)
    assert not switch_holds(ledger)


@pytest.mark.parametrize('response', ['returned bytes', {'stdout': 'returned bytes'}, {'stdout': 'returned bytes', 'exit_code': 0}])
def test_successful_chain_uses_host_completion_without_requiring_exit_field(response):
    ledger = Ledger()
    events = pair('Bash', {'command': "sed -i 's/old/new/' loom.py && python3 loom.py"})
    events[1]['tool_response'] = response
    feed(ledger, events)
    assert not switch_holds(ledger)


def test_redirect_does_not_displace_mutator_operand():
    ledger = Ledger()
    call(ledger, "sed -i 's/old/new/' loom.py > log.txt; python3 loom.py > result.txt")
    assert not switch_holds(ledger)
    assert 'file:/w/loom.py' in ledger.written
    assert 'file:/w/log.txt' in ledger.written
    assert 'file:/w/result.txt' in ledger.written


@pytest.mark.parametrize('path,command', [('loom.py', 'echo ready; python3 loom.py'), ('loom.toml', 'echo ready; cat loom.toml')])
def test_compound_call_started_before_external_edit_does_not_pay(path, command):
    ledger = Ledger()
    events = pair('Bash', {'command': command}, 'returned bytes', tid='overlap')
    feed(ledger, events[:1])
    feed(ledger, edit(path))
    feed(ledger, events[1:])
    assert switch_holds(ledger)


def test_host_effects_and_complete_reads_keep_their_call_scope():
    ledger = Ledger()
    events = pair('Bash', {'command': 'opaque_write'}, 'written', tid='host-write')
    events[0]['makoto'] = {'effects': [{'subject': 'loom.toml'}]}
    feed(ledger, events)
    assert switch_holds(ledger)
    events = pair('Bash', {'command': 'opaque_read'}, 'full bytes', tid='host-read')
    events[1]['makoto'] = {'reads': [{'subject': 'loom.toml', 'complete': True}]}
    feed(ledger, events)
    assert not switch_holds(ledger)


@pytest.mark.parametrize('code,paid', [
    ("import tomllib; print(tomllib.load(open('loom.toml','rb')))", True),
    ("import tomllib; print('loom.toml')", False),
    ("import tomllib; print(lambda: tomllib.load(open('loom.toml','rb')))", False),
    ("import tomllib; print(tomllib.load(open('other.toml','rb')))", False),
])
def test_inline_config_consumption_requires_literal_unconditional_load(code, paid):
    import shlex
    ledger = Ledger()
    feed(ledger, edit('loom.toml'))
    call(ledger, 'python -c ' + shlex.quote(code))
    assert bool(switch_holds(ledger)) != paid


@pytest.mark.parametrize('variant', ['execute', 'read_only', 'quoted', 'conditional', 'wrong_path'])
def test_inline_node_vm_execution_has_exact_builtin_call_shape(variant):
    import shlex
    ledger = Ledger()
    feed(ledger, edit('loom.js'))
    code = "require('node:vm').runInNewContext(require('node:fs').readFileSync('loom.js','utf8'), {console})"
    if variant == 'read_only':
        code = "require('node:fs').readFileSync('loom.js','utf8')"
    elif variant == 'quoted':
        code = 'console.log(' + __import__('json').dumps(code) + ')'
    elif variant == 'conditional':
        code = 'if (false) ' + code
    elif variant == 'wrong_path':
        code = code.replace('loom.js', 'other.js')
    call(ledger, 'node -e ' + shlex.quote(code))
    assert bool(switch_holds(ledger)) == (variant != 'execute')


@pytest.mark.parametrize('runner', ['awk -f loom.awk', 'gawk --file=loom.awk', 'mawk -floom.awk'])
@pytest.mark.parametrize('reverse', [False, True])
def test_awk_script_operand_and_order(runner, reverse):
    ledger = Ledger()
    segments = ["sed -i 's/old/new/' loom.awk", runner]
    if reverse:
        segments.reverse()
    call(ledger, '; '.join(segments))
    assert bool(switch_holds(ledger)) == reverse


def test_awk_readback_or_other_script_does_not_pay():
    ledger = Ledger()
    call(ledger, "cat loom.awk; sed -i 's/old/new/' loom.awk; awk -f other.awk")
    assert switch_holds(ledger)


@pytest.mark.parametrize('reverse', [False, True])
def test_formatter_write_participates_in_order(reverse):
    ledger = Ledger()
    commands = ['gofmt -w loom.go', 'go run loom.go']
    if reverse:
        commands.reverse()
    call(ledger, '; '.join(commands))
    assert bool(switch_holds(ledger)) == reverse


def test_package_version_before_sentence_verb_is_not_a_physical_unit(tmp_path):
    s = Session(tmp_path)
    s.feed(pair(text='Sapling 8.4'))
    assert held(s.send(output('Sapling 8.4 is a tool.')))
    assert s.rules() == {'c'}
    s.feed(pair('WebSearch', {'query': 'Sapling 8.4'}, 'Sapling 8.4 is a tool.', tid='online'))
    assert not held(s.send(output('Sapling 8.4 is a tool.')))
