"""Recorded dependent steps replayed through the in-process hook (D23)."""
import json
from pathlib import Path

import pytest

from test_shapes import Session, event
from run_pairs import held

CASES = json.loads((Path(__file__).parent / 'data' / 'recorded-cases.json').read_text())


# Open cases: no D-line meets the recorded label, and his words have not settled it
# (held definitions, prose-only failures, a path given as a value). Strict marks
# keep a later change from silently flipping one.
CONFLICTS = {
    'h009': 'D6/D17: the landing read explicitly records branch grove-preview, not the claimed grove-release.',
    'h030': 'D16: the attachment path is mentioned in a register but never read itself.',
    'h553': 'D16: the attachment path is mentioned in a register but never read itself.',
    'h611': 'D16: the attachment path is mentioned in a register but never read itself.',
    'h126': 'D4/D13: the matched Read returns an error sentence without a failure event or structured failure signal.',
    'h147': 'D4/D13: the matched Read returns an error sentence without a failure event or structured failure signal.',
    'i005': 'D15/D16/D18: the acceptance subject/value are read; no host-held definition or behavior claim requires more evidence.',
    'i035': 'D15/D16/D18: the acceptance subject/value are read; no host-held definition or behavior claim requires more evidence.',
    'i071': 'D15/D16/D18: the acceptance subject/value are read; no host-held definition or behavior claim requires more evidence.',
    'i031': 'D1/D16: the actual commit-message argument names an acceptance subject already read; no host-held definition exists.',
}
PARAMETERS = [pytest.param(case, id=case['id'], marks=(
    pytest.mark.xfail(strict=True, reason=CONFLICTS[case['id']])
    if case['id'] in CONFLICTS else ())) for case in CASES]


@pytest.mark.parametrize('case', PARAMETERS)
def test_recorded(tmp_path, case):
    events = [dict(event(row['hook_event_name']), **row) for row in case['events']]
    transcript = tmp_path / 'history.jsonl'
    transcript.write_text(''.join(json.dumps(row) + '\n' for row in events[:-1]))
    response = Session(tmp_path).send(dict(events[-1], transcript_path=str(transcript)))
    assert held(response) == (case['expect'] == 'hold'), (case['why'], response)
