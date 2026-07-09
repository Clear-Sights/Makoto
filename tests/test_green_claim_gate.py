"""A3 sentinels — gate.green_claim: a whole-suite green claim contradicted by a recorded red run.

Three surfaces:
  - whole_suite_pass_claim (lib.claims): the prose half (whole-suite green claim, subset/negation/forward/code-safe)
  - green_claim_gate: the conjunction (claim AND latest testrun output is a real failure)
  - run_stop_checks: end-to-end through a real in-memory ledger (the live integration path)
"""
from __future__ import annotations
import sqlite3

from makoto.substrate.claims import whole_suite_pass_claim
from makoto.checks.falseGreenClaim import green_claim_gate
from makoto._dispatch import run_stop_checks
from makoto.record import ledger as L
# === whole_suite_pass_claim: the whole-suite green claim ==============================

def test_signal_tp_whole_suite_claims():
    for s in ["tests pass", "all tests pass", "the tests pass", "tests passed",
              "the suite passes", "the test suite is green", "the full test suite passes",
              "CI is green", "tests are passing", "tests now pass", "the build passes"]:
        assert whole_suite_pass_claim(s), s


def test_signal_neg_subset_claims():
    """a SUBSET subject (a slice of the suite) is an honest partial claim -> silent."""
    for s in ["parser tests pass", "these tests pass", "unit tests pass",
              "the auth tests pass", "integration test suite passes",
              "the integration test suite passes", "smoke tests pass"]:
        assert not whole_suite_pass_claim(s), s


def test_signal_neg_enumerated_count_claims():
    """an ENUMERATED count ('N tests passing') is a COUNT, not a universal claim — out of scope
    (quantity-matching was cut as un-FP-safe). This is the real corpus FP: '244 tests passing
    (4 pre-existing failures)' is an honest caveated count, NOT 'the suite is green'."""
    assert not whole_suite_pass_claim("**244 tests passing** (4 pre-existing failures, tracked)")
    assert not whole_suite_pass_claim("All 53 tests pass.")
    assert not whole_suite_pass_claim("22 tasks complete  **244 tests passing** now")
    assert not whole_suite_pass_claim("126 tests pass, 20-edge registry built")


def test_signal_neg_negated_forward_singular():
    assert not whole_suite_pass_claim("tests do not pass")
    assert not whole_suite_pass_claim("not all tests pass yet")
    assert not whole_suite_pass_claim("once tests pass I'll commit")
    assert not whole_suite_pass_claim("will the tests pass after this?")
    assert not whole_suite_pass_claim("the test passed")            # singular -> not the whole suite


def test_signal_neg_code_quoted():
    assert not whole_suite_pass_claim("the log line `=== tests pass ===` is printed")
    assert not whole_suite_pass_claim("```\ntests pass\n```")


# === green_claim_gate: claim AND recorded red run =================================

def test_gate_fires_green_claim_over_red_run():
    f = green_claim_gate("All tests pass now.",
                         testrun_output="=== 3 failed, 678 passed in 12.3s ===")
    assert f is not None and f.pattern_id == "gate.green_claim"


def test_gate_silent_when_run_green():
    assert green_claim_gate("All tests pass.",
                            testrun_output="=== 681 passed in 12.3s ===") is None


def test_gate_silent_on_xfail_run():
    """the xfail wall: an expected-fail run is green-with-expected-fails -> no contradiction."""
    assert green_claim_gate("All tests pass.",
                            testrun_output="=== 681 passed, 3 xfailed in 2.1s ===") is None


def test_gate_silent_when_no_runner_output():
    assert green_claim_gate("All tests pass.", testrun_output="") is None


def test_gate_silent_on_subset_claim_over_red():
    assert green_claim_gate("The parser tests pass.",
                            testrun_output="=== 3 failed in 1s ===") is None


def test_empty_text_never_fabricates_a_green_claim():
    # a tool-only turn (no assistant prose) carries NO claim — empty text must stay inert even with a
    # red run on record. Orthogonality: the `if not text: return None` guard in whole_suite_pass_claim
    # is the sole behavioral killer of its `return None -> return Match` mutant (which would fire the
    # gate on an empty string + a failing run — a claim fabricated from nothing).
    assert whole_suite_pass_claim("") is None
    assert green_claim_gate("", testrun_output="=== 3 failed in 1s ===") is None


# === run_stop_checks: end-to-end through a real ledger =============================

def _conn():
    c = sqlite3.connect(":memory:", isolation_level=None)
    c.execute("CREATE TABLE commitments (commitment_key TEXT PRIMARY KEY, session_id TEXT, "
              "location TEXT, qty_min REAL, qty_max REAL, status TEXT NOT NULL DEFAULT 'open', "
              "retract_param TEXT, created_event_id INTEGER, ts TEXT)")
    c.execute("CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT NOT NULL, "
              "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)")
    return c


def _bash(c, cmd, stdout, ev_id, sid="s"):
    L.record_update(c, {"tool_name": "Bash", "tool_input": {"command": cmd},
                        "tool_response": {"stdout": stdout, "stderr": "", "exitCode": 1}},
                    event_id=ev_id, session_id=sid)


def test_e2e_fires_on_green_claim_after_red_pytest():
    c = _conn()
    _bash(c, "python -m pytest tests/ -q", "=== 2 failed, 9 passed in 4.0s ===", 1)
    findings = run_stop_checks(c, {"last_assistant_message": "Done — all tests pass.",
                                  "session_id": "s", "cwd": "/repo"})
    assert any(f.pattern_id == "gate.green_claim" for f in findings)


def test_e2e_silent_after_fix_and_rerun_green():
    """red run, then a fix-and-rerun GREEN under a different key: the most-recent testrun is green
    -> NO fire. This is the dominant honest-corpus shape A must not false-block."""
    c = _conn()
    _bash(c, "python -m pytest tests/auth.py", "=== 1 failed in 1.0s ===", 1)
    _bash(c, "python -m pytest tests/ -q", "=== 12 passed in 4.0s ===", 2)   # re-run, later ts/ev
    findings = run_stop_checks(c, {"last_assistant_message": "Fixed — all tests pass now.",
                                  "session_id": "s", "cwd": "/repo"})
    assert not any(f.pattern_id == "gate.green_claim" for f in findings)


def test_e2e_silent_when_cat_a_log_not_a_runner():
    """a `cat failing.log` printing a failure summary is NOT a testrun row -> gate silent."""
    c = _conn()
    L.record_update(c, {"tool_name": "Bash", "tool_input": {"command": "cat tests/old.log"},
                        "tool_response": {"stdout": "=== 9 failed in 2s ===", "stderr": "",
                                          "exitCode": 0}}, event_id=1, session_id="s")
    findings = run_stop_checks(c, {"last_assistant_message": "All tests pass.",
                                  "session_id": "s", "cwd": "/repo"})
    assert not any(f.pattern_id == "gate.green_claim" for f in findings)
