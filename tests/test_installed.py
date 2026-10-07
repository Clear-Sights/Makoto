"""The marketplace plugin layout and exact installed shell commands."""
import json

import pytest

from test_built_pairs import CASES, build
from test_shapes import Session
from makoto2 import hook
from run_pairs import held
from hook_timings import install, replay_installed


@pytest.fixture(scope='module')
def installed(tmp_path_factory):
    return install(tmp_path_factory.mktemp('installed') / 'plugin')


@pytest.mark.parametrize('rule,kind,variant', CASES)
def test_installed_pair(tmp_path, installed, rule, kind, variant):
    for clean in (False, True):
        events, proposed = build(rule, kind, variant, clean)
        session = Session(tmp_path / f'in-process-{clean}')
        state = tmp_path / f'installed-{clean}'
        for event, response, _ in replay_installed(installed, state, events + [proposed]):
            expected = session.send(event)
            assert response == json.dumps(expected).encode()
        response = json.loads(response)
        assert held(response) == (not clean)
        journal = hook.sigma_read(hook.sigma_path(state, proposed['session_id']), proposed['session_id'])
        assert {f['rule'] for f in journal[-1]['findings']} == (set() if clean else set(rule))
        if clean:
            # D25: admitted writers receive context; admitted finals are empty.
            assert response == hook.questions(proposed)
            if proposed['hook_event_name'] == 'Stop':
                assert response == {}


@pytest.mark.parametrize('failure', ['unset', 'missing-root', 'import'])
def test_broken_install(tmp_path, failure):
    from hook_timings import invoke, routes
    from test_shapes import event
    plugin = install(tmp_path / 'plugin')
    commands = routes(plugin)
    if failure == 'import':
        (plugin / 'makoto2/evaluate.py').unlink()
    target = None if failure == 'unset' else tmp_path / 'absent' if failure == 'missing-root' else plugin
    for name, route in commands.items():
        for command in route:
            result, _ = invoke(command, json.dumps(event(name)).encode(), target, tmp_path / 'state')
            assert b'makoto' in result.stderr, result.stderr
            if name in ('PreToolUse', 'Stop', 'SubagentStop'):
                # A dependent step or final answer holds when the hook cannot run.
                assert result.returncode == 2, result
            else:
                # A ledger-only event never blocks the user; it says loudly that it was not recorded.
                assert result.returncode == 0, result
                assert json.loads(result.stdout)['systemMessage'].startswith('makoto: hook failed'), result.stdout


def test_clean_event(tmp_path, installed):
    from test_shapes import event
    responses = list(replay_installed(installed, tmp_path / 'state', [event('Stop', last_assistant_message='Thank you!')]))
    assert responses[0][1] == b'{}'
