"""makoto.checks.staleEstablisher -- the opt-in ADVISORY (never blocking) ground-truth
staleness detector (SPEC-5). Falsifying tests for the check() logic itself, and a structural
proof that it can never block: it is not discovered by stopchecks.load_stopchecks (no GATE
export), so its pattern_id can never enter _dispatch._blocking_gate_ids().
"""
from __future__ import annotations

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
    """Structural proof of the never-BLOCK guarantee: staleEstablisher has no GATE export, so
    load_stopchecks() never discovers it -- and separately, its CHECK's own posture is never
    BLOCK, so it can't enter _dispatch._blocking_gate_ids() (load_checks(edge="Stop")-derived,
    SPEC-C item 2) either way -- its pattern_id can never enter the blocking-eligible set,
    regardless of the level its own Finding carries."""
    from makoto.substrate._loader import load_stopchecks
    assert not hasattr(staleEstablisher, "GATE")
    assert "gate.stale_establisher" not in {g.id for g in load_stopchecks()}


def test_check_export_is_advisory_and_stop_scoped():
    assert staleEstablisher.CHECK.id == "gate.stale_establisher"
    assert staleEstablisher.CHECK.applies_at == "Stop"
    from makoto.verdict.posture import ADVISE
    assert staleEstablisher.CHECK.posture == ADVISE
