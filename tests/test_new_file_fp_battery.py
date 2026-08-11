"""Adversarial NEW-FILE battery for the 9 AST-introduced patterns (Bug B + falsifiability #3).

The AST-introduced factory (substrate.factories.ast_introduced_predicate) has NO file-existence gate: a
brand-new Write fires purely on the introduced AST shape. Investigation flagged this as a possible
false-positive vector ("a new file shouldn't fire"). The closer truth — proven here per pattern —
is two-sided, and the resolution is NO code change (narrowing would VIOLATE monotonicity):

  (A) MONOTONICITY direction: firing on newly-written insecure/hollow code is the DESIGN, not a bug.
      A real violation introduced as a brand-new file MUST still fire — else the "no file-existence
      gate" would be a hole a writer could exploit by always creating fresh files. Each pattern's
      canonical violation, written to a NEW path, is asserted to fire.

  (B) FP direction: the legitimate "new repro / new test file" class that motivated the worry
      (`assert False`, `assert 0`, an xfail repro, a non-verifier early `return True`) matches NONE
      of the 9 shipped patterns — content.verifier_body_hollowed needs a TRUTHY-hollow body on the integrity-checks PATH (an
      always-FAIL `assert False` is not hollow; a test path is off-surface), and the security/crypto
      patterns key on insecure API shapes a repro file does not contain. Asserted silent across all 9.

This converts the latent corpus-FP=0 (an underpowered null on near-dead surfaces) into explicit,
per-pattern adversarial teeth. The teeth test proves a neutered predicate would be caught.
"""
from __future__ import annotations

from makoto.core.schema import PreCheck
from makoto.checks.envGatedAudit import predicate as p_1_2
from makoto.checks.verifierBodyHollowed import predicate as p_1_27
# certVerifyDisabled/jwtSignatureDisabled/certNoneMode/timingUnsafeCompare/jwtNoneAlg/
# paramikoHostKeyWeakened/certReqsNone moved to Ward, 2026-07-13 (github.com/Clear-Sights/Ward) --
# their new-file FP-battery coverage moved with them (see Ward's own tests/test_checks.py).


def _pat(pid: str) -> PreCheck:
    return PreCheck(id=pid, fire_level="error", description=f"pattern {pid}", retry_hint="x")


# (predicate, pattern, NEW file path, canonical real-violation content) — TP shapes are the exact
# proven-firing strings from each pattern's own sentinel, re-pathed to a brand-new file.
_VIOLATIONS = [
    (p_1_2,  "content.env_gated_audit",  "new_app.py",
     "if os.environ.get('ENABLE_AUDIT_TRAIL'):\n    write_audit_trail()\n"),
    (p_1_27, "content.verifier_body_hollowed", "constitution/integrity/checks/new_seal.py",
     "def verify_seal(state):\n    return True\n"),
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
    FP class a retired authorship-attribution prototype tripped on — proven absent from the shipped signal."""
    fires = []
    for path, content in _LEGIT_NEW_FILES:
        for pred, pid, _p, _c in _VIOLATIONS:
            if _fires(pred, pid, path, content):
                fires.append((pid, path))
    assert not fires, f"legit new-file write false-fired (real FP — narrow ONLY if monotonicity-safe): {fires}"


def test_legit_secure_near_misses_silent():
    """Per-pattern legit near-miss: the SECURE counterpart of each violation stays silent."""
    near = [
        # content.verifier_body_hollowed: a genuine verifier body (real comparison logic, not a
        # truthy-hollow body) on the same integrity-checks path stays silent.
        (p_1_27, "content.verifier_body_hollowed", "constitution/integrity/checks/new_seal.py",
         "def verify_seal(state):\n    return state.hash == state.expected_hash\n"),
    ]
    fired = [pid for pred, pid, path, content in near if _fires(pred, pid, path, content)]
    assert not fired, f"secure near-miss false-fired: {fired}"


def test_battery_has_teeth():
    """A neutered predicate (always None) does NOT fire on a violation the real predicate DOES fire
    on — so test_real_violation_fires_when_written_as_new_file would go RED on such a regression."""
    pred, pid, path, content = _VIOLATIONS[1]  # content.verifier_body_hollowed truthy-hollow body
    assert _fires(pred, pid, path, content)               # real predicate fires
    dead = lambda **k: None                                # neutered
    assert not _fires(dead, pid, path, content)           # neuter -> silent -> battery catches it
