"""Removing one check cannot change any byte emitted by the other three."""
import importlib
import json

import pytest
from test_built_pairs import CASES, build, replay

MODULE = importlib.import_module('makoto2.evaluate')
FUNCTIONS = {'a': 'lineage', 'b': 'spec', 'c': 'other', 'd': 'switch'}


def encoded(findings, omitted):
    return json.dumps([f for f in findings if f['rule'] != omitted], ensure_ascii=False).encode()


@pytest.mark.parametrize('disabled', 'abcd')
@pytest.mark.parametrize('rule,kind,variant', CASES)
@pytest.mark.parametrize('clean', [False, True])
def test_disable_one(monkeypatch, disabled, rule, kind, variant, clean):
    # DESIGN D19: decision functions neither mutate nor gate one another.
    events, proposed = build(rule, kind, variant, clean)
    baseline = replay(events, proposed)
    monkeypatch.setattr(MODULE, FUNCTIONS[disabled], lambda *args: [])
    reduced = replay(events, proposed)
    assert all(f['rule'] != disabled for f in reduced)
    assert encoded(reduced, disabled) == encoded(baseline, disabled)
