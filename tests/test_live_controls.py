"""Controls for ported live scope and launcher fixes."""
import pytest

from test_shapes import event, pair, output
from test_switch import feed, edit, switch_holds
from makoto2.provenance import Ledger
from makoto2.evaluate import evaluate


@pytest.mark.parametrize('ran', [False, True])
def test_push_checks_committed_revision_and_ignores_later_scratch(ran):
    ledger = Ledger()
    feed(ledger, edit('included.py'))
    if ran:
        feed(ledger, pair('Run', {'file_path': 'included.py'}, 'response', tid='run'))
    feed(ledger, pair('Bash', {'command': 'git add included.py'}, '', tid='add'))
    # A native record may contain a commit made before the hook was installed.
    feed(ledger, pair('Bash', {'command': 'git commit -m Update'}, 'committed', tid='commit'))
    feed(ledger, edit('scratch.py', tid='scratch'))
    assert bool(switch_holds(ledger, output('Done', 'push'))) == (not ran)
    assert switch_holds(ledger, output('Done'))  # Finals still select scratch.


@pytest.mark.parametrize('mode,response', [
    ('sh -n', {'stdout': 'checked', 'exitCode': 0}),
    ('bash -c', {'stdout': 'evaluated', 'exitCode': 0}),
    ('sh', {'backgroundTaskId': 'job', 'content': 'queued'}),
    ('sh', {'running': True, 'content': 'queued'}),
    ('sh', None),
])
def test_launcher_check_eval_or_unfinished_output_cannot_pay(mode, response):
    """discriminant: a codex-job.sh launch whose payload never really ran the script"""
    ledger = Ledger()
    feed(ledger, edit('worker.sh'))
    call = pair('Bash', {'command': 'sh codex-job.sh start job -- ' + mode + ' worker.sh'}, tid='launcher')
    call[1]['tool_response'] = response
    feed(ledger, call)
    assert switch_holds(ledger)


@pytest.mark.parametrize('command', ['git commit --only worker.py -m Update',
                                     'git add worker.py && git commit -m Update'])
def test_candidate_scope_never_becomes_completed_evidence(command):
    ledger = Ledger()
    feed(ledger, edit('worker.py'))
    candidate = event('PreToolUse', tool_name='Bash', tool_use_id='candidate', tool_input={'command': command})
    assert switch_holds(ledger, candidate)
    assert not ledger.staged_code and not ledger.committed_code and not ledger.executions


def test_new_writer_names_do_not_clear_existing_unread_references():
    ledger = Ledger()
    ledger.ingest(event('UserPromptSubmit', prompt='unread.txt'))
    candidate = event('PreToolUse', tool_name='Write', tool_use_id='create',
                      tool_input={'file_path': 'new.py', 'content': 'value = "unread.txt"\n'})
    findings, _ = evaluate(ledger, candidate)
    assert 'b' in {f['rule'] for f in findings}


def test_rename_preserves_config_readback_in_public_code():
    ledger = Ledger()
    feed(ledger, edit('old.json'))
    feed(ledger, pair(ti={'file_path': 'old.json'}, text='{}', tid='readback'))
    feed(ledger, pair('Bash', {'command': 'mv old.json new.json'}, '', tid='rename'))
    assert not switch_holds(ledger)


def test_rename_writer_alias_still_selects_unrun_source():
    ledger = Ledger()
    feed(ledger, edit('old_worker.py'))
    feed(ledger, pair('Bash', {'command': 'mv old_worker.py new_worker.py'}, '', tid='rename'))
    assert switch_holds(ledger, output('new_worker', 'Write'))


def test_rename_cannot_use_overwritten_destination_run():
    """discriminant: an mv onto a destination whose only run was of the overwritten file"""
    ledger = Ledger()
    feed(ledger, edit('source.py'))
    feed(ledger, edit('destination.py', tid='destination'))
    feed(ledger, pair('Run', {'file_path': 'destination.py'}, 'response', tid='run-destination'))
    feed(ledger, pair('Bash', {'command': 'mv source.py destination.py'}, '', tid='rename'))
    assert switch_holds(ledger)
