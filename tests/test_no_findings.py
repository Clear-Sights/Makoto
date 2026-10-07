"""Invented clean/faulty twins at every planned dependent boundary."""
import shlex

import pytest

from test_shapes import Session, output, pair
from run_pairs import held


@pytest.mark.parametrize('boundary', ['Write', 'Edit', 'commit', 'Stop'])
@pytest.mark.parametrize('subject', [
    'amber_271', 'birch_382', 'cobalt_493',
    'dahlia_514', 'elm_625', 'flint_736',
])
@pytest.mark.parametrize('read', [False, True], ids=['faulty', 'clean'])
def test_findings_alone_hold(tmp_path, boundary, subject, read):
    session = Session(tmp_path)
    session.feed(pair(text=subject if read else 'source data'))
    candidate = output(subject, boundary)
    if boundary == 'commit':
        candidate['tool_input']['command'] = 'git commit -m ' + shlex.quote(subject)
    candidate['stop_hook_active'] = False
    response = session.send(candidate)
    assert held(response) == (not read)
    assert session.rules() == (set() if read else {'a', 'b'})
    if read and boundary == 'Stop':
        assert response == {}
