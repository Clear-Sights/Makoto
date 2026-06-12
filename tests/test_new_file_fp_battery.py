"""Adversarial NEW-FILE battery for the 9 AST-introduced patterns (Bug B + falsifiability #3).

The AST-introduced factory (lib.factories.ast_introduced_predicate) has NO file-existence gate: a
brand-new Write fires purely on the introduced AST shape. Investigation flagged this as a possible
false-positive vector ("a new file shouldn't fire"). The closer truth — proven here per pattern —
is two-sided, and the resolution is NO code change (narrowing would VIOLATE monotonicity):

  (A) MONOTONICITY direction: firing on newly-written insecure/hollow code is the DESIGN, not a bug.
      A real violation introduced as a brand-new file MUST still fire — else the "no file-existence
      gate" would be a hole a writer could exploit by always creating fresh files. Each pattern's
      canonical violation, written to a NEW path, is asserted to fire.

  (B) FP direction: the legitimate "new repro / new test file" class that motivated the worry
      (`assert False`, `assert 0`, an xfail repro, a non-verifier early `return True`) matches NONE
      of the 9 shipped patterns — 1.27 needs a TRUTHY-hollow body on the integrity-checks PATH (an
      always-FAIL `assert False` is not hollow; a test path is off-surface), and the security/crypto
      patterns key on insecure API shapes a repro file does not contain. Asserted silent across all 9.

This converts the latent corpus-FP=0 (an underpowered null on near-dead surfaces) into explicit,
per-pattern adversarial teeth. The teeth test proves a neutered predicate would be caught.
"""
from __future__ import annotations

from makoto.schema import PreCheck
from makoto.prechecks.precheck_1_2 import predicate as p_1_2
from makoto.prechecks.precheck_1_26 import predicate as p_1_26
from makoto.prechecks.precheck_1_27 import predicate as p_1_27
from makoto.prechecks.precheck_1_28 import predicate as p_1_28
from makoto.prechecks.precheck_1_29 import predicate as p_1_29
from makoto.prechecks.precheck_1_30 import predicate as p_1_30
from makoto.prechecks.precheck_1_31 import predicate as p_1_31
from makoto.prechecks.precheck_1_32 import predicate as p_1_32
from makoto.prechecks.precheck_1_33 import predicate as p_1_33


def _pat(pid: str) -> PreCheck:
    return PreCheck(id=pid, fire_level="error", description=f"pattern {pid}", retry_hint="x")


# (predicate, pattern, NEW file path, canonical real-violation content) — TP shapes are the exact
# proven-firing strings from each pattern's own sentinel, re-pathed to a brand-new file.
_VIOLATIONS = [
    (p_1_2,  "1.2",  "new_app.py",
     "if os.environ.get('ENABLE_AUDIT_TRAIL'):\n    write_audit_trail()\n"),
    (p_1_26, "1.26", "new_client.py",
     "import requests\nr = requests.get(url, verify=False)\n"),
    (p_1_27, "1.27", "constitution/integrity/checks/new_seal.py",
     "def verify_seal(state):\n    return True\n"),
    (p_1_28, "1.28", "new_auth.py",
     "import jwt\ndata = jwt.decode(token, key, verify=False)\n"),
    (p_1_29, "1.29", "new_net.py",
     "import ssl\nctx.verify_mode = ssl.CERT_NONE\n"),
    (p_1_30, "1.30", "new_mac.py",
     "if hmac.new(key, body).hexdigest() == sig:\n    ok()\n"),
    (p_1_31, "1.31", "new_svc.py",
     'import jwt\njwt.decode(token, key, algorithms=["none"])\n'),
    (p_1_32, "1.32", "new_ssh.py",
     "import paramiko\nclient.set_missing_host_key_policy(paramiko.AutoAddPolicy())\n"),
    (p_1_33, "1.33", "new_tls.py",
     "import ssl\nssl.wrap_socket(sock, cert_reqs=ssl.CERT_NONE)\n"),
]

# Legitimate brand-new-file writes that motivated the FP worry — must stay silent everywhere.
_LEGIT_NEW_FILES = [
    ("tests/test_bug_repro.py", "def test_repro():\n    assert False\n"),
    ("tests/test_edge.py",      "def test_edge():\n    assert 0\n"),
    ("tests/test_xfail.py",     "import pytest\n@pytest.mark.xfail\ndef test_known():\n    assert False\n"),
    ("util/nullobj.py",         "class Null:\n    def get(self):\n        return True\n"),
    ("scratch/notes.py",        "x = 1\ndef helper():\n    return True\n"),
]


def _fires(pred, pid: str, file_path: str, content: str) -> bool:
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": file_path, "content": content}}
    return pred(current_event=evt, history=[], pattern=_pat(pid)) is not None


def test_real_violation_fires_when_written_as_new_file():
    """(A) Monotonicity: every pattern's real violation, introduced as a BRAND-NEW file, fires.
    The absence of a file-existence gate is intentional and must NOT be silently suppressible."""
    missed = [pid for pred, pid, path, content in _VIOLATIONS
              if not _fires(pred, pid, path, content)]
    assert not missed, f"real new-file violations went silent (would be a monotonicity hole): {missed}"


def test_legit_new_repro_file_is_silent_across_all_patterns():
    """(B) The legit new-test/new-repro class (assert False / assert 0 / xfail / null-object
    return True) matches NONE of the 9 AST-introduced patterns. This is the heredoc-new-repro-file
    FP class the cut 1.34 prototype tripped on — proven absent from the shipped signal."""
    fires = []
    for path, content in _LEGIT_NEW_FILES:
        for pred, pid, _p, _c in _VIOLATIONS:
            if _fires(pred, pid, path, content):
                fires.append((pid, path))
    assert not fires, f"legit new-file write false-fired (real FP — narrow ONLY if monotonicity-safe): {fires}"


def test_legit_secure_near_misses_silent():
    """Per-pattern legit near-miss: the SECURE counterpart of each violation stays silent."""
    near = [
        (p_1_26, "1.26", "new_client.py", "import requests\nr = requests.get(url, verify=True)\n"),
        (p_1_28, "1.28", "new_auth.py",   "import jwt\ndata = jwt.decode(token, key, algorithms=['HS256'])\n"),
        (p_1_29, "1.29", "new_net.py",    "import ssl\nctx.verify_mode = ssl.CERT_REQUIRED\n"),
        (p_1_31, "1.31", "new_svc.py",    'jwt.decode(token, key, algorithms=["HS256"])\n'),
        (p_1_32, "1.32", "new_ssh.py",    "client.set_missing_host_key_policy(paramiko.RejectPolicy())\n"),
        (p_1_33, "1.33", "new_tls.py",    "ssl.wrap_socket(sock, cert_reqs=ssl.CERT_REQUIRED)\n"),
        # 1.30: a non-crypto equality in a new test file (no STRONG token) stays silent.
        (p_1_30, "1.30", "tests/test_calc.py", "def test_sum():\n    assert result == expected\n"),
    ]
    fired = [pid for pred, pid, path, content in near if _fires(pred, pid, path, content)]
    assert not fired, f"secure near-miss false-fired: {fired}"


def test_battery_has_teeth():
    """A neutered predicate (always None) does NOT fire on a violation the real predicate DOES fire
    on — so test_real_violation_fires_when_written_as_new_file would go RED on such a regression."""
    pred, pid, path, content = _VIOLATIONS[1]  # 1.26 verify=False
    assert _fires(pred, pid, path, content)               # real predicate fires
    dead = lambda **k: None                                # neutered
    assert not _fires(dead, pid, path, content)           # neuter -> silent -> battery catches it
