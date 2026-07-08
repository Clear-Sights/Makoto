"""makoto.checks._planNode -- pure PlanNode/Plan port from Assay's plan/node.py + plan/gaps.py
(SPEC-5). Falsifying tests for the GAP rule (deps as gaps read by passthrough-name, no DAG),
mark_done/resolve, passthrough_locations, remainder, and the rows/from_rows/from_jsonl codec.
"""
from __future__ import annotations

import pytest

from makoto.checks._planNode import DONE, OPEN, Plan, PlanNode


def test_plannode_id_defaults_to_composite():
    n = PlanNode(what="Write", passthrough="auth.py", where="/repo/auth.py")
    assert n.id == "Write::auth.py::/repo/auth.py"
    assert n.status == OPEN


def test_plannode_explicit_id_is_kept():
    n = PlanNode(what="Write", passthrough="x", where="/r/x", id="custom")
    assert n.id == "custom"


def test_add_node_identical_redeclare_is_noop():
    plan = Plan()
    a = plan.add_node("Write", "auth.py", "/repo/auth.py")
    b = plan.add_node("Write", "auth.py", "/repo/auth.py")
    assert a is b
    assert len(plan.nodes()) == 1


def test_add_node_same_id_different_shape_raises():
    plan = Plan()
    plan.add_node("Write", "auth.py", "/repo/auth.py", id="fixed")
    with pytest.raises(ValueError):
        plan.add_node("Edit", "auth.py", "/repo/auth.py", id="fixed")


def test_mark_done_advances_status_leaves_triple_untouched():
    plan = Plan()
    n = plan.add_node("Write", "auth.py", "/repo/auth.py")
    plan.mark_done(n.id)
    got = plan.nodes()[0]
    assert got.status == DONE
    assert got.what == "Write" and got.passthrough == "auth.py" and got.where == "/repo/auth.py"


def test_mark_done_unknown_id_raises_keyerror():
    with pytest.raises(KeyError):
        Plan().mark_done("nope")


def test_resolve_prefers_open_node_over_done_at_same_where():
    plan = Plan()
    first = plan.add_node("Write", "a", "/r/a", id="n1")
    plan.mark_done(first.id)
    second = plan.add_node("Edit", "a", "/r/a", id="n2")
    assert plan.resolve("/r/a") == second.id


def test_resolve_no_match_returns_none():
    assert Plan().resolve("/nowhere") is None


def test_establisher_has_no_unmet_deps():
    plan = Plan()
    n = plan.add_node("Write", "auth.py", "/repo/auth.py")
    assert plan.unmet_deps(n.id) == set()
    assert plan.order_violation(n.id) is False


def test_dependent_on_open_establisher_is_unmet_gap():
    plan = Plan()
    establisher = plan.add_node("Write", "auth.py", "/repo/auth.py", id="e1")
    dependent = plan.add_node("Edit", "auth.py", "/repo/auth2.py", id="d1")
    assert plan.unmet_deps(dependent.id) == {"e1"}
    assert plan.order_violation(dependent.id) is True


def test_dependent_on_done_establisher_has_no_gap():
    plan = Plan()
    establisher = plan.add_node("Write", "auth.py", "/repo/auth.py", id="e1")
    plan.mark_done(establisher.id)
    dependent = plan.add_node("Edit", "auth.py", "/repo/auth2.py", id="d1")
    assert plan.unmet_deps(dependent.id) == set()
    assert plan.order_violation(dependent.id) is False


def test_passthrough_locations_multiset():
    plan = Plan()
    plan.add_node("Write", "auth.py", "/repo/auth.py")
    plan.add_node("Edit", "auth.py", "/repo/other.py")
    assert plan.passthrough_locations() == {"auth.py": {"/repo/auth.py", "/repo/other.py"}}


def test_remainder_is_open_node_ids():
    plan = Plan()
    a = plan.add_node("Write", "a", "/r/a", id="a")
    plan.add_node("Write", "b", "/r/b", id="b")
    plan.mark_done("a")
    assert plan.remainder() == {"b"}


def test_rows_roundtrip_via_from_rows():
    plan = Plan()
    plan.add_node("Write", "auth.py", "/repo/auth.py", id="n1")
    plan.mark_done("n1")
    rebuilt = Plan.from_rows(plan.rows())
    assert rebuilt.rows() == plan.rows()
    assert rebuilt.nodes()[0].status == DONE


def test_from_jsonl_parses_lines_preserving_order():
    text = (
        '{"id":"n1","what":"Write","passthrough":"a","where":"/r/a","status":"done"}\n'
        '{"id":"n2","what":"Edit","passthrough":"a","where":"/r/b","status":"open"}\n'
    )
    plan = Plan.from_jsonl(text)
    ids = [n.id for n in plan.nodes()]
    assert ids == ["n1", "n2"]
    assert plan.order_violation("n2") is False   # n1 (establisher) is DONE


def test_from_jsonl_skips_blank_lines():
    text = '{"id":"n1","what":"Write","passthrough":"a","where":"/r/a"}\n\n'
    plan = Plan.from_jsonl(text)
    assert len(plan.nodes()) == 1
