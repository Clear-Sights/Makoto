"""makoto.session.plan -- sqlite persistence for a declared contract Plan (SPEC-5). Falsifying tests
for declare_plan's falsifiability gate + latest-wins semantics, load_plan's fail-open reads,
and declare_from_session_artifact's SessionStart admission (STARTUP-only, fail-open on a bad
artifact, fail-closed on a non-falsifiable one).
"""
from __future__ import annotations

import sqlite3

import pytest

from makoto.record import db
from makoto.session import plan as plan_store
from makoto.substrate._planNode import DONE, Plan


@pytest.fixture
def conn(tmp_path):
    state_dir = tmp_path / "state"
    db.init_db(state_dir, tmp_path / "CITATIONS.md")
    c = sqlite3.connect(str(state_dir / "makoto.record.db"))
    yield c
    c.close()


def test_declare_then_load_roundtrips(conn):
    p = Plan()
    p.add_node("Write", "auth.py", "/repo/auth.py")
    plan_store.declare_plan(conn, "s1", p)
    loaded = plan_store.load_plan(conn, "s1")
    assert loaded is not None
    assert loaded.rows() == p.rows()


def test_load_plan_absent_session_returns_none(conn):
    assert plan_store.load_plan(conn, "ghost") is None


def test_declare_plan_rejects_non_falsifiable_node_whole(conn):
    p = Plan()
    p.add_node("", "auth.py", "/repo/auth.py")   # empty `what` -> non-falsifiable
    with pytest.raises(ValueError):
        plan_store.declare_plan(conn, "s1", p)
    assert plan_store.load_plan(conn, "s1") is None   # whole declare rejected, nothing persisted


def test_declare_plan_is_latest_wins(conn):
    first = Plan()
    first.add_node("Write", "a", "/r/a", id="n1")
    plan_store.declare_plan(conn, "s1", first)
    second = Plan()
    second.add_node("Write", "b", "/r/b", id="n2")
    plan_store.declare_plan(conn, "s1", second)
    loaded = plan_store.load_plan(conn, "s1")
    assert [n.id for n in loaded.nodes()] == ["n2"]


def test_persist_plan_saves_advanced_status_without_falsifiability_recheck(conn):
    p = Plan()
    p.add_node("Write", "a", "/repo/a.py", id="n1")
    plan_store.declare_plan(conn, "s1", p)
    loaded = plan_store.load_plan(conn, "s1")
    loaded.mark_done("n1")
    plan_store.persist_plan(conn, "s1", loaded)
    reloaded = plan_store.load_plan(conn, "s1")
    assert reloaded.nodes()[0].status == DONE


def test_declare_from_session_artifact_absent_file_is_none(conn, tmp_path):
    got = plan_store.declare_from_session_artifact(str(tmp_path), "s1", conn, source="startup")
    assert got is None


def test_declare_from_session_artifact_wrong_source_is_none(conn, tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "makoto-plan.jsonl").write_text(
        '{"what":"Write","passthrough":"a","where":"a.py"}\n'
    )
    assert plan_store.declare_from_session_artifact(str(tmp_path), "s1", conn, source="resume") is None
    assert plan_store.load_plan(conn, "s1") is None


def test_declare_from_session_artifact_admits_on_startup(conn, tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "makoto-plan.jsonl").write_text(
        '{"what":"Write","passthrough":"a","where":"a.py"}\n'
    )
    got = plan_store.declare_from_session_artifact(str(tmp_path), "s1", conn, source="startup")
    assert got is not None
    assert len(got.rows()) == 1
    assert plan_store.load_plan(conn, "s1") is not None


def test_declare_from_session_artifact_malformed_json_is_none(conn, tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "makoto-plan.jsonl").write_text("not json at all\n")
    assert plan_store.declare_from_session_artifact(str(tmp_path), "s1", conn, source="startup") is None


def test_declare_from_session_artifact_non_falsifiable_node_rejects_whole(conn, tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "makoto-plan.jsonl").write_text(
        '{"what":"","passthrough":"a","where":"a.py"}\n'
    )
    assert plan_store.declare_from_session_artifact(str(tmp_path), "s1", conn, source="startup") is None
    assert plan_store.load_plan(conn, "s1") is None
