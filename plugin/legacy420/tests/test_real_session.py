"""Minimal, sanitized witnesses from the operator-labelled real session."""
import json
from pathlib import Path
import re

import pytest

from test_goal import run_payloads

CASES = json.loads((Path(__file__).parent/'fixtures/real_session.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_real_session(case, tmp_path):
    side = 'fake' if case['label'] == 'REAL' else 'honest'
    response = run_payloads(case, side, tmp_path/'session')
    if side == 'honest':
        assert response == {}, response
    else:
        assert response['hookSpecificOutput']['permissionDecision'] == 'deny'
        assert re.search(r'\b(?:C12|R11)\b', response['hookSpecificOutput']['permissionDecisionReason'])
