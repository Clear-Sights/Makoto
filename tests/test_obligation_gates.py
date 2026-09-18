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
from makoto.checks.unreadStructure import unread_structure_gate
from makoto.checks.unwitnessedScanner import unwitnessed_verifier_gate
from makoto.checks.unknownRefSwitch import unknown_ref_switch_gate
from makoto.checks.unobservedDestruction import unobserved_destruction_gate
from makoto.checks.relaunchedUnchanged import relaunched_unchanged_gate


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

# ---- the second batch: one register entry each ------------------------------------------------

def _bash(command, stdout=""):
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                        "tool_input": {"command": command},
                        "tool_response": {"stdout": stdout, "exitCode": 0}}}


# gate.unread_structure (register A3 POSITIONAL PAIRING)

def test_unread_structure_fires_on_a_null_traversal():
    f = unread_structure_gate([_bash("jq '.a.b' config.json", "null")])
    assert f is not None and f.level == "advisory"


def test_unread_structure_is_silent_after_a_structure_query():
    assert unread_structure_gate([_bash("jq 'keys' config.json", '["a"]'),
                                  _bash("jq '.a.b' config.json", "null")]) is None


def test_unread_structure_is_silent_on_a_non_null_result():
    assert unread_structure_gate([_bash("jq '.a' config.json", "42")]) is None


def test_unread_structure_is_silent_on_empty_output():
    """A named recall bound, tested so it stays deliberate: an empty stdout is what a great many
    correct commands produce, so only a literal JSON `null` as the whole output counts."""
    assert unread_structure_gate([_bash("jq '.a' config.json", "")]) is None


def test_unread_structure_needs_null_to_be_the_whole_output():
    """`null` inside a larger result is data, not a failed traversal."""
    assert unread_structure_gate([_bash("jq '.' config.json", '{"a": null}')]) is None


# gate.unwitnessed_verifier (register B4 WRONG ORACLE)

def test_unwitnessed_verifier_fires_on_a_first_clean_run():
    f = unwitnessed_verifier_gate([_bash("pytest -q", "58 passed in 2.0s")])
    assert f is not None and f.level == "advisory"


def test_unwitnessed_verifier_is_silent_once_the_verifier_has_been_seen_failing():
    assert unwitnessed_verifier_gate([_bash("pytest -q", "1 failed, 57 passed"),
                                      _bash("pytest -q", "58 passed")]) is None


def test_unwitnessed_verifier_still_fires_when_the_red_run_came_after():
    assert unwitnessed_verifier_gate([_bash("pytest -q", "58 passed"),
                                      _bash("pytest -q", "1 failed")]) is not None


def test_unwitnessed_verifier_reads_zero_failed_as_a_clean_report():
    """The regression this test exists for: `re.I` over `\\bFAILED\\b` matched the WORD "failed",
    so "58 passed, 0 failed" read as the verifier FIRING and the gate went quiet on exactly the
    report it exists for. The counted form is anchored to a non-zero count and the bare report
    tokens are case-sensitive."""
    assert unwitnessed_verifier_gate([_bash("pytest -q", "58 passed, 0 failed")]) is not None


def test_unwitnessed_verifier_is_silent_on_a_command_that_is_not_a_verifier():
    assert unwitnessed_verifier_gate([_bash("ls -la", "OK")]) is None


# gate.unknown_ref_switch (register D12 PRESERVE TO VOLATILE)

def test_unknown_ref_switch_fires_on_an_unprinted_ref():
    f = unknown_ref_switch_gate([_bash("git checkout feature-x")])
    assert f is not None and f.level == "advisory"


def test_unknown_ref_switch_is_silent_after_the_refs_were_printed():
    for printer in ("git branch", "git rev-parse --verify feature-x", "git show-ref"):
        assert unknown_ref_switch_gate([_bash(printer), _bash("git switch feature-x")]) is None


def test_unknown_ref_switch_ignores_a_file_restore():
    """`git checkout -- <path>` restores a file and moves no ref, so it is not the boundary."""
    assert unknown_ref_switch_gate([_bash("git checkout -- src/a.py")]) is None


def test_unknown_ref_switch_does_not_accept_status_or_log_as_the_print():
    """Neither names the ref being switched TO, which is the whole point of the guard."""
    assert unknown_ref_switch_gate([_bash("git status"), _bash("git checkout x")]) is not None
    assert unknown_ref_switch_gate([_bash("git log --oneline"), _bash("git checkout x")]) is not None


# gate.unobserved_destruction (register D14 UNDO UNPROVEN)

def test_unobserved_destruction_fires_with_no_verifier():
    f = unobserved_destruction_gate([_bash("rm -rf build/")])
    assert f is not None and f.level == "advisory"


def test_unobserved_destruction_is_silent_after_a_verifier_ran():
    assert unobserved_destruction_gate([_bash("pytest -q", "58 passed"),
                                        _bash("rm -rf build/")]) is None


def test_unobserved_destruction_takes_either_verdict_as_the_observation():
    """Keel's U20 asks for a report, PASS or FAIL: either is a behaviour observation, and only
    the absence of both leaves an undo unprovable."""
    assert unobserved_destruction_gate([_bash("pytest -q", "1 failed"),
                                        _bash("rm -rf build/")]) is None


def test_unobserved_destruction_inherits_the_one_destructive_classifier():
    """`substrate._canonAtoms._is_destructive_argv` is the single home, so its documented scope
    cut is inherited whole: long-form `rm` stays outside the short-option form."""
    assert unobserved_destruction_gate([_bash("git reset --hard HEAD~1")]) is not None
    assert unobserved_destruction_gate([_bash("ls -la")]) is None


# gate.relaunched_unchanged (register E13 PARKED ON AN INHERITED CHANNEL)

def test_relaunched_unchanged_is_silent_on_a_single_launch():
    """The first launch owes nothing -- that is the act the clause exists to permit, and
    `min_acts=2` is what makes it so."""
    assert relaunched_unchanged_gate([_row("Task")]) is None


def test_relaunched_unchanged_fires_on_the_second_launch():
    f = relaunched_unchanged_gate([_row("Task"), _row("Task")])
    assert f is not None and f.level == "advisory"


def test_relaunched_unchanged_is_silent_after_a_verifier_ran():
    assert relaunched_unchanged_gate([_bash("pytest -q", "58 passed"),
                                      _row("Task"), _row("Task")]) is None


def test_relaunched_unchanged_is_distinct_from_unprobed_fanout():
    """docs/MERGE-WITNESSES.tsv claims a Read plus two dispatches fires this gate and not
    gate.unprobed_fanout -- the read pays that gate's obligation and nothing paid this one.
    WITHOUT the read, unprobed_fanout catches the same input and would subsume this gate, so
    the claim is only as good as this test."""
    with_read = [_row("Read", file_path="/repo/parser.py"), _row("Task"), _row("Task")]
    assert relaunched_unchanged_gate(with_read) is not None
    assert unprobed_fanout_gate(with_read) is None
    without_read = [_row("Task"), _row("Task")]
    assert unprobed_fanout_gate(without_read) is not None
