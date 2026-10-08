"""Transport failures hold the first Stop but must not hold its retry."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin'))
from makoto2 import hook


@pytest.fixture
def failing_transport(monkeypatch, tmp_path):
    def fail_read(path, session_id):
        raise ValueError('forced journal failure')

    monkeypatch.setattr(hook, 'sigma_read', fail_read)
    return {'state_dir': str(tmp_path / 'state')}


@pytest.mark.parametrize('event_name', ['Stop', 'SubagentStop'])
@pytest.mark.parametrize('active', [True, False])
def test_stop_transport_failure(event_name, active, failing_transport):
    event = dict(hook_event_name=event_name, session_id='s', stop_hook_active=active)
    response = hook.main(json.dumps(event), failing_transport)
    if active:
        assert response.get('decision') != 'block'
        assert response == {
            'systemMessage': 'makoto transport/contract failure (not held twice): forced journal failure'
        }
    else:
        assert response == {
            'decision': 'block',
            'reason': 'makoto transport/contract failure: forced journal failure',
        }


@pytest.mark.parametrize('active', [True, False])
def test_pretool_transport_failure_still_denies(active, failing_transport):
    event = dict(hook_event_name='PreToolUse', session_id='s',
                 tool_use_id='t1', stop_hook_active=active)
    assert hook.main(json.dumps(event), failing_transport) == {
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': 'makoto transport/contract failure: forced journal failure',
        }
    }
