"""pattern 1.32 sentinels — AUTO-GENERATED from predict_check.py predictions (1.32 paramiko set_missing_host_key_policy(AutoAddPolicy/WarningPolicy) — host-key verification weakened).

TP = honest-looking real violations that MUST fire; NEG = honest code that MUST stay silent.
Regenerated deterministically from the candidate's predicted_tp/fp inputs — hand-edit only to add cases.
"""
from __future__ import annotations
from makoto.prechecks.precheck_1_32 import predicate
from makoto.schema import PreCheck

_PAT = PreCheck(id="1.32", fire_level="error", description='1.32 paramiko set_missing_host_key_policy(AutoAddPolicy/WarningPolicy) — host-key verification weakened', retry_hint="x")


def _run(file_path, key, value):
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": file_path, key: value}}
    return predicate(current_event=evt, history=[], pattern=_PAT) is not None


def test_tp_0():
    assert _run('ssh.py', 'content', 'import paramiko\nclient.set_missing_host_key_policy(paramiko.AutoAddPolicy())\n')

def test_tp_1():
    assert _run('ssh.py', 'content', 'client.set_missing_host_key_policy(AutoAddPolicy())\n')

def test_tp_2():
    assert _run('ssh.py', 'content', 'client.set_missing_host_key_policy(paramiko.WarningPolicy)\n')

def test_tp_3():
    assert _run('ssh.py', 'content', 'client.set_missing_host_key_policy(WarningPolicy())\n')

def test_neg_0():
    assert not _run('ssh.py', 'content', 'client.set_missing_host_key_policy(paramiko.RejectPolicy())\n')

def test_neg_1():
    assert not _run('ssh.py', 'content', 'client.set_missing_host_key_policy(RejectPolicy())\n')

def test_neg_2():
    assert not _run('ssh.py', 'content', 'client.set_missing_host_key_policy(policy)\n')

def test_neg_3():
    assert not _run('ssh.py', 'content', '# client.set_missing_host_key_policy(AutoAddPolicy())\n')

def test_neg_4():
    assert not _run('ssh.py', 'content', 'client.set_missing_host_key_policy(AutoAddPolicy())  # makoto-allow: throwaway test fixture against a local sshd\n')

def test_neg_5():
    assert not _run('ssh.py', 'content', 'register(AutoAddPolicy())\n')
