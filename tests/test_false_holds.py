"""Observed false holds replay clean; each fake twin is still held.

Cases come from live refusals in the Countdown project (2026-10-09). The same
file feeds tools/measure_rates.py for before/after catch and false-hold rates.
"""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'plugin'), str(ROOT / 'tools')]
from measure_rates import replay

CASES = json.loads((ROOT / 'tests' / 'fixtures' / 'false_holds.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_honest_twin_is_not_held(case):
    held, fired = replay(case['honest'], case.get('files'), case.get('transcript_honest'))
    assert not held, fired


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_fake_twin_is_still_held_by_the_same_rule(case):
    held, fired = replay(case['fake'], case.get('files'), case.get('transcript_fake'))
    assert case['rule'] in fired
