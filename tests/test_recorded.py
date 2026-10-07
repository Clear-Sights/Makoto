"""Recorded dependent steps replayed through the in-process hook (D23)."""
import json
from pathlib import Path

import pytest

from test_shapes import Session, event
from run_pairs import held

CASES = json.loads((Path(__file__).parent / 'data' / 'recorded-cases.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=[case['id'] for case in CASES])
def test_recorded(tmp_path, case):
    events = [dict(event(row['hook_event_name']), **row) for row in case['events']]
    transcript = tmp_path / 'history.jsonl'
    transcript.write_text(''.join(json.dumps(row) + '\n' for row in events[:-1]))
    response = Session(tmp_path).send(dict(events[-1], transcript_path=str(transcript)))
    assert held(response) == (case['expect'] == 'hold'), (case['why'], response)
