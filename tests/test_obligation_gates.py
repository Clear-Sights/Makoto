"""ACT_VS_GUARD: the obligation shape, and the two gates that are the first of it.

`kit.unmet_obligation_gate` holds an ACT against a guard that had to come first. Nothing else in
this catalog does that -- every other check holds the assistant's STATEMENT against the record --
so ORDER is the whole check, and these tests exist to make the order falsifiable. The closing
text is empty in every case below, on purpose: a turn that says nothing at all can still owe.
"""
from __future__ import annotations

from makoto.kit import unmet_obligation_gate
from makoto.checks.unprobedFanout import unprobed_fanout_gate
from makoto.checks.unaskedPlan import unasked_plan_gate


def _row(tool_name, **ti):
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": tool_name,
                        "tool_input": ti, "tool_response": {"stdout": "", "exitCode": 0}}}


# ---- gate.unprobed_fanout (register B11 BASELINE UNTAKEN) -------------------------------------

def test_unprobed_fanout_fires_on_a_dispatch_with_no_read():
    f = unprobed_fanout_gate([_row("Task", description="refactor the parser")])
    assert f is not None
    assert f.pattern_id == "gate.unprobed_fanout"
    assert f.level == "advisory"


def test_unprobed_fanout_is_silent_when_a_read_came_first():
    f = unprobed_fanout_gate([_row("Read", file_path="/repo/parser.py"),
                              _row("Task", description="refactor the parser")])
    assert f is None


def test_unprobed_fanout_still_fires_when_the_read_came_after():
    """The ORDER is the check. A read after the dispatch does not pay the obligation, because the
    brief was already written from assumption and the work is inherited whole. Collapsing this
    into "a read appears somewhere in the session" is the one way to hollow this gate, so it has
    its own test."""
    f = unprobed_fanout_gate([_row("Task", description="refactor the parser"),
                              _row("Read", file_path="/repo/parser.py")])
    assert f is not None


def test_unprobed_fanout_accepts_glob_and_grep_as_the_probe():
    for probe in ("Glob", "Grep"):
        assert unprobed_fanout_gate([_row(probe, pattern="parse"),
                                     _row("Task", description="x")]) is None


def test_unprobed_fanout_is_silent_on_a_session_with_no_dispatch():
    assert unprobed_fanout_gate([_row("Bash", command="ls")]) is None
    assert unprobed_fanout_gate([]) is None
    assert unprobed_fanout_gate(None) is None


def test_unprobed_fanout_treats_agent_as_the_same_act_as_task():
    assert unprobed_fanout_gate([_row("Agent", description="x")]) is not None


# ---- gate.unasked_plan (register G2 DETERMINED ASKED AS OPEN) ---------------------------------

def test_unasked_plan_fires_on_a_plan_with_no_question():
    f = unasked_plan_gate([_row("ExitPlanMode", plan="step 1, step 2")])
    assert f is not None
    assert f.pattern_id == "gate.unasked_plan"
    assert f.level == "advisory"


def test_unasked_plan_is_silent_when_a_question_came_first():
    f = unasked_plan_gate([_row("AskUserQuestion", questions="which target?"),
                           _row("ExitPlanMode", plan="step 1")])
    assert f is None


def test_unasked_plan_still_fires_when_the_question_came_after():
    """Same order law: asking after the plan is fixed does not unfix it."""
    f = unasked_plan_gate([_row("ExitPlanMode", plan="step 1"),
                           _row("AskUserQuestion", questions="which target?")])
    assert f is not None


def test_unasked_plan_is_silent_on_a_session_with_no_plan():
    assert unasked_plan_gate([_row("Read", file_path="/repo/x.py")]) is None


# ---- the two gates are distinct, which is what their merge witnesses claim -------------------

def test_each_gate_is_silent_on_the_other_s_witness_input():
    """docs/MERGE-WITNESSES.tsv claims each of these gates is silent on the input that fires the
    other. That claim is only as good as a test, so here it is."""
    task_only = [_row("Task", description="x")]
    plan_only = [_row("ExitPlanMode", plan="step 1")]
    assert unprobed_fanout_gate(task_only) is not None
    assert unasked_plan_gate(task_only) is None
    assert unasked_plan_gate(plan_only) is not None
    assert unprobed_fanout_gate(plan_only) is None


# ---- the factory's own contract ---------------------------------------------------------------

def test_factory_fails_open_on_an_undecodable_row():
    """An undecodable row could BE the guard, so it must never push the gate toward firing."""
    g = unmet_obligation_gate(
        act=lambda ev: ev.get("tool_name") == "A", guard=lambda ev: ev.get("tool_name") == "G",
        pattern_id="gate.test", message="m", retry_hint="r")
    assert g(["not a row at all", {"no": "payload"}]) is None


def test_factory_min_acts_fires_only_from_the_nth_unguarded_act():
    """For a clause whose costly thing is the REPEAT rather than the first one (Keel's U02)."""
    g = unmet_obligation_gate(
        act=lambda ev: ev.get("tool_name") == "A", guard=lambda ev: ev.get("tool_name") == "G",
        pattern_id="gate.test", message="m", retry_hint="r", min_acts=2)
    assert g([_row("A")]) is None
    assert g([_row("A"), _row("A")]) is not None


def test_factory_a_guard_pays_every_later_act_in_the_session():
    """Keel's window is `session` and its subject is `session_id`: one guard pays the session,
    not one act. A per-act obligation would be a different clause and would need its own row."""
    g = unmet_obligation_gate(
        act=lambda ev: ev.get("tool_name") == "A", guard=lambda ev: ev.get("tool_name") == "G",
        pattern_id="gate.test", message="m", retry_hint="r")
    assert g([_row("G"), _row("A"), _row("A"), _row("A")]) is None
