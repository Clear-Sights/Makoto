"""pattern 1.33 sentinels — AUTO-GENERATED from predict_check.py predictions (1.33 cert_reqs=ssl.CERT_NONE kwarg — peer-cert verification disabled at the call site).

TP = honest-looking real violations that MUST fire; NEG = honest code that MUST stay silent.
Regenerated deterministically from the candidate's predicted_tp/fp inputs — hand-edit only to add cases.
"""
from __future__ import annotations
from makoto.checks.certReqsNone import predicate
from makoto.core.schema import PreCheck

_PAT = PreCheck(id="content.cert_reqs_none", fire_level="error", description='1.33 cert_reqs=ssl.CERT_NONE kwarg — peer-cert verification disabled at the call site', retry_hint="x")


def _run(file_path, key, value):
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": file_path, key: value}}
    return predicate(current_event=evt, history=[], pattern=_PAT) is not None


def test_tp_0():
    assert _run('tls.py', 'content', 'import ssl\nssl.wrap_socket(sock, cert_reqs=ssl.CERT_NONE)\n')

def test_tp_1():
    assert _run('tls.py', 'content', 'context.wrap_socket(sock, cert_reqs=CERT_NONE)\n')

def test_tp_2():
    assert _run('tls.py', 'content', 'urllib3.PoolManager(cert_reqs=ssl.CERT_NONE)\n')

def test_neg_0():
    assert not _run('tls.py', 'content', 'ssl.wrap_socket(sock, cert_reqs=ssl.CERT_REQUIRED)\n')

def test_neg_1():
    assert not _run('tls.py', 'content', 'context.wrap_socket(sock, cert_reqs=ssl.CERT_OPTIONAL)\n')

def test_neg_2():
    assert not _run('tls.py', 'content', 'pool = PoolManager(cert_reqs="CERT_NONE")\n')

def test_neg_3():
    assert not _run('tls.py', 'content', 'ctx.verify_mode = ssl.CERT_NONE\n')

def test_neg_4():
    assert not _run('tls.py', 'content', '# ssl.wrap_socket(sock, cert_reqs=ssl.CERT_NONE)\n')

def test_neg_5():
    assert not _run('tls.py', 'content', 'ssl.wrap_socket(sock, cert_reqs=ssl.CERT_NONE)  # makoto-allow: localhost test client, no CA available\n')
