"""makoto.checks.staleEstablisher -- the opt-in ADVISORY (never blocking) ground-truth
staleness detector (SPEC-5). Falsifying tests for the check() logic itself, and a structural
proof that it can never block: its CHECK export stays `may_block=False` (2026-07-10, retiring
`load_stopchecks()`/`GATE`), so its pattern_id can never enter dispatch._blocking_gate_ids()
regardless of what `.level` its own Finding carries.
"""
from __future__ import annotations

import json

from makoto.checks import staleEstablisher
from makoto.substrate._planNode import Plan


def test_check_is_none_when_no_plan_declared():
    assert staleEstablisher.check(None) is None


def test_check_fires_when_done_establisher_file_is_gone(tmp_path):
    missing = tmp_path / "gone.py"   # never created
    plan = Plan()
    plan.add_node("Write", "gone.py", str(missing), id="establisher")
    plan.mark_done("establisher")
    plan.add_node("Edit", "gone.py", str(tmp_path / "other.py"), id="dependent")
    finding = staleEstablisher.check(plan)
    assert finding is not None
    assert finding.pattern_id == "gate.stale_establisher"
    assert finding.level == "advisory"
    assert "gone.py" in finding.message or str(missing) in finding.message


def test_check_clean_when_establisher_file_still_exists(tmp_path):
    present = tmp_path / "here.py"
    present.write_text("x = 1\n")
    plan = Plan()
    plan.add_node("Write", "here.py", str(present), id="establisher")
    plan.mark_done("establisher")
    plan.add_node("Edit", "here.py", str(tmp_path / "other.py"), id="dependent")
    assert staleEstablisher.check(plan) is None


def test_check_clean_when_no_dependent_shares_the_passthrough(tmp_path):
    missing = tmp_path / "gone.py"
    plan = Plan()
    plan.add_node("Write", "gone.py", str(missing), id="establisher")
    plan.mark_done("establisher")   # DONE, missing on disk, but NO later node shares its name
    assert staleEstablisher.check(plan) is None


def test_check_clean_when_establisher_still_open():
    plan = Plan()
    plan.add_node("Write", "x.py", "/repo/x.py", id="establisher")   # still open, not DONE
    plan.add_node("Edit", "x.py", "/repo/other.py", id="dependent")
    assert staleEstablisher.check(plan) is None


def test_never_discovered_as_a_blocking_stop_gate():
    """Structural proof of the never-BLOCK guarantee: staleEstablisher's CHECK stays
    may_block=False, so it never enters dispatch._blocking_gate_ids() (load_checks(edge="Stop")-
    derived, filtered on may_block) regardless of what `.level` its own Finding carries."""
    assert staleEstablisher.CHECK.may_block is False
    from makoto.registry import load_checks
    live_ids = {c.id for c in load_checks(edge="Stop") if c.may_block}
    assert "gate.stale_establisher" not in live_ids


def test_a_stale_establisher_finding_does_not_block_when_dispatch_runs_it(
        monkeypatch, capsys, state_dir):
    """The BEHAVIOURAL half of the never-BLOCK guarantee, through the real dispatch call site.

    `test_never_discovered_as_a_blocking_stop_gate` above reads `CHECK.may_block` and then reads
    the same field again through `load_checks(edge="Stop")`. That is a sound structural argument
    and it stays -- but every step of it is a DECLARATION. It does not observe the dispatcher, so
    it cannot tell whether `_evaluate_and_gate` actually consults `_blocking_gate_ids()` when it
    decides what to block on. If that filter were dropped, every gate finding would reach the
    decision and this gate would block at level "error" with the tests above still green.

    An earlier version of this test wrote the filter expression out by hand and called
    `_emit_decision` directly, which left exactly that hole: deleting the call site inside the
    dispatcher would not have reddened it. This one calls `_evaluate_and_gate` itself, on a real
    connection and a real Stop payload, with `run_stop_checks` replaced by one returning a
    Finding that carries THIS gate's pattern_id at the worst level the vocabulary has. Whatever
    the dispatcher does with a gate finding, it does here.

    The control is in the same test and is the point: the identical Finding under a
    blocking-eligible pattern_id must produce a blocking decision through the same path, so a
    dispatcher that has stopped emitting anything at all cannot pass this either.
    """
    import sqlite3
    from makoto import dispatch as D

    blocking = D._blocking_gate_ids()
    assert blocking, "no gate is blocking-eligible at all; the control below would be vacuous"
    control_id = sorted(blocking)[0]

    payload = {"hook_event_name": "Stop", "session_id": "stale-establisher-test",
               "cwd": str(state_dir), "last_assistant_message": "done"}

    def drive(pattern_id):
        planted = D.Finding(pattern_id=pattern_id, file="x.py", line=1, level="error",
                            message="planted", retry_hint="")
        monkeypatch.setattr(D, "run_stop_checks", lambda *a, **k: [planted])
        monkeypatch.setattr(D, "_gates_enabled", lambda *a, **k: True)
        conn = sqlite3.connect(str(state_dir / "makoto.record.db"), isolation_level=None)
        try:
            capsys.readouterr()
            D._evaluate_and_gate(conn, payload, json.dumps(payload), 1, state_dir)
        finally:
            conn.close()
        return capsys.readouterr().out

    assert drive(control_id), (
        f"the control gate {control_id} produced no decision at level error through "
        f"_evaluate_and_gate; this test cannot distinguish 'not blocking' from 'nothing blocks'")
    assert drive("gate.stale_establisher") == "", (
        "a stale-establisher finding at level error reached the decision through the real "
        "dispatch path; the never-BLOCK guarantee is a claim about behaviour, and this is the "
        "behaviour")


def test_check_export_is_advisory_and_stop_scoped():
    assert staleEstablisher.CHECK.id == "gate.stale_establisher"
    assert staleEstablisher.CHECK.applies_at == "Stop"
    from makoto.verdict import ADVISE
    assert staleEstablisher.CHECK.posture == ADVISE
