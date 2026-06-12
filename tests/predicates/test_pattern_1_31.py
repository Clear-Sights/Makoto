"""pattern 1.31 sentinels — AUTO-GENERATED from predict_check.py predictions (1.31 jwt decode algorithms=["none"] — unsigned-alg whitelist (alg-confusion bypass)).

TP = honest-looking real violations that MUST fire; NEG = honest code that MUST stay silent.
Regenerated deterministically from the candidate's predicted_tp/fp inputs — hand-edit only to add cases.
"""
from __future__ import annotations
from makoto.prechecks.precheck_1_31 import predicate
from makoto.schema import PreCheck

_PAT = PreCheck(id="1.31", fire_level="error", description='1.31 jwt decode algorithms=["none"] — unsigned-alg whitelist (alg-confusion bypass)', retry_hint="x")


def _run(file_path, key, value):
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": file_path, key: value}}
    return predicate(current_event=evt, history=[], pattern=_PAT) is not None


def test_tp_0():
    assert _run('svc.py', 'content', 'import jwt\njwt.decode(token, key, algorithms=["none"])\n')

def test_tp_1():
    assert _run('svc.py', 'content', 'jwt.decode(token, algorithms=["HS256", "none"])\n')

def test_tp_2():
    assert _run('svc.py', 'content', 'jose.jwt.decode(t, k, algorithms=["None"])\n')

def test_tp_3():
    assert _run('svc.py', 'content', 'pyjwt.decode(t, algorithms=("none",))\n')

def test_neg_0():
    assert not _run('svc.py', 'content', 'jwt.decode(token, key, algorithms=["HS256"])\n')

def test_neg_1():
    assert not _run('svc.py', 'content', 'codec.decode(data, algorithms=["none"])\n')

def test_neg_2():
    assert not _run('svc.py', 'content', 'jwt.encode(payload, key, algorithm="none")\n')

def test_neg_3():
    assert not _run('svc.py', 'content', '# jwt.decode(token, algorithms=["none"])\n')

def test_neg_4():
    assert not _run('svc.py', 'content', 'jwt.decode(t, algorithms=["none"])  # makoto-allow: unit test asserts the none-alg path is rejected\n')

def test_neg_5():
    assert not _run('svc.py', 'content', 'jwt.decode(token, key, algorithms=algs)\n')
