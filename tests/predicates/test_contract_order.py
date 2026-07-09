"""makoto.checks.contractOrder -- the declared-Plan gap/stop guard (SPEC-5). Falsifying tests
for the PRE gap-guard predicate (blocks a locating call that advances a node whose establisher
isn't DONE) and the STOP remainder GATE (blocks a turn ending with the plan unfinished).
"""
from __future__ import annotations

import sqlite3

import pytest

from makoto.record import db
from makoto.session import plan as plan_store
from makoto.checks import contractOrder
from makoto.substrate._planNode import Plan
from makoto.core.schema import PreCheck


@pytest.fixture
def conn(tmp_path):
    state_dir = tmp_path / "state"
    db.init_db(state_dir, tmp_path / "CITATIONS.md")
    c = sqlite3.connect(str(state_dir / "makoto.record.db"))
    yield c
    c.close()


_PATTERN = PreCheck(
    id="gate.contract_order", fire_level="error", description="",
    retry_hint="finish the establisher first", predicate_module="makoto.checks.contractOrder",
    keywords=["file_path"],
)


def _event(tool_name, file_path, session_id="s1"):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path},
        "session_id": session_id,
    }


def test_predicate_ignores_events_with_no_declared_plan(conn):
    finding = contractOrder.predicate(
        current_event=_event("Write", "/repo/auth.py"), history=[], pattern=_PATTERN, conn=conn)
    assert finding is None


def test_predicate_ignores_non_pretooluse_events(conn):
    p = Plan()
    p.add_node("Edit", "auth.py", "/repo/other.py", id="dependent")
    plan_store.declare_plan(conn, "s1", p)
    ev = _event("Edit", "/repo/other.py")
    ev["hook_event_name"] = "PostToolUse"
    assert contractOrder.predicate(current_event=ev, history=[], pattern=_PATTERN, conn=conn) is None


def test_predicate_blocks_a_call_whose_establisher_is_unmet(conn):
    p = Plan()
    p.add_node("Write", "auth.py", "/repo/auth.py", id="establisher")   # still open
    p.add_node("Edit", "auth.py", "/repo/other.py", id="dependent")
    plan_store.declare_plan(conn, "s1", p)
    finding = contractOrder.predicate(
        current_event=_event("Edit", "/repo/other.py"), history=[], pattern=_PATTERN, conn=conn)
    assert finding is not None
    assert finding.pattern_id == "gate.contract_order"
    assert finding.level == "error"
    assert "establisher" in finding.message


def test_predicate_clean_when_establisher_is_done(conn):
    p = Plan()
    p.add_node("Write", "auth.py", "/repo/auth.py", id="establisher")
    p.add_node("Edit", "auth.py", "/repo/other.py", id="dependent")
    plan_store.declare_plan(conn, "s1", p)
    loaded = plan_store.load_plan(conn, "s1")
    loaded.mark_done("establisher")
    plan_store.persist_plan(conn, "s1", loaded)
    finding = contractOrder.predicate(
        current_event=_event("Edit", "/repo/other.py"), history=[], pattern=_PATTERN, conn=conn)
    assert finding is None


def test_predicate_clean_for_a_non_locating_tool():
    finding = contractOrder.predicate(
        current_event={"hook_event_name": "PreToolUse", "tool_name": "Bash",
                       "tool_input": {"command": "ls"}, "session_id": "s1"},
        history=[], pattern=_PATTERN, conn=None)
    assert finding is None


def test_stop_gate_fires_on_open_remainder():
    plan = Plan()
    plan.add_node("Write", "auth.py", "/repo/auth.py", id="n1")
    finding = contractOrder.GATE.run(_FakeCtx(plan))
    assert finding is not None
    assert finding.pattern_id == "gate.contract_order"
    assert finding.level == "error"


def test_stop_gate_clean_when_plan_fully_done():
    plan = Plan()
    plan.add_node("Write", "auth.py", "/repo/auth.py", id="n1")
    plan.mark_done("n1")
    assert contractOrder.GATE.run(_FakeCtx(plan)) is None


def test_stop_gate_clean_when_no_plan_declared():
    assert contractOrder.GATE.run(_FakeCtx(None)) is None


class _FakeCtx:
    """A minimal stand-in exposing only the `.plan` attribute contractOrder's GATE reads."""

    def __init__(self, plan):
        self.plan = plan
