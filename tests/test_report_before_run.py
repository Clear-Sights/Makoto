"""gate.report_before_run (register C11 REPORT BEFORE DECIDE) -- the order, and the two firewalls.

The check is an ORDER law, so the first group is the order itself: the same write, before and
after a run. The second group is the target firewall (prose is a report; code is data), and the
third is the three false-positive guards the tree's hardened prose reader supplies for free --
a subset claim, a negation, and a forward frame are not reports of an outcome.
"""
from __future__ import annotations

import pytest

from makoto.checks.switch import report_CHECK as CHECK, _reports_a_run_verdict, report_before_run_gate


def _prose_write(path, content, tool_name="Write"):
    key = {"Write": "content", "Edit": "new_string"}.get(tool_name, "content")
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": tool_name,
                        "tool_input": {"file_path": path, key: content},
                        "tool_response": {}}}


def _run(command="python3 -m pytest -q", stdout="58 passed in 2.0s"):
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                        "tool_input": {"command": command},
                        "tool_response": {"stdout": stdout, "exitCode": 0}}}


# ---- the order ------------------------------------------------------------------------------

def test_fires_on_a_report_with_no_run_before_it():
    """The scenario tests/test_stop_gate_level_invariant.py names for this gate."""
    finding = report_before_run_gate([_prose_write("HANDOFF.md", "The suite passes.")])
    assert finding is not None
    assert finding.pattern_id == "gate.report_before_run"
    assert finding.level == "advisory"


def test_silent_when_the_run_came_first():
    assert report_before_run_gate([_run(), _prose_write("HANDOFF.md", "The suite passes.")]) is None


def test_still_fires_when_the_run_came_AFTER_the_report():
    """The order IS the check. A run that follows the report does not retroactively make the
    report a reading of it -- which is the whole content of the register's rule, so a gate that
    only asked "did a run happen in this session" would pass the fault it exists for."""
    assert report_before_run_gate(
        [_prose_write("HANDOFF.md", "The suite passes."), _run()]) is not None


def test_the_first_run_discharges_every_later_prose_write():
    """The guard is whole-session, deliberately: pairing a document to the run it describes is a
    referent judgement this tree declines. Once something ran, later reports are silent."""
    history = [_run(), _prose_write("A.md", "The suite passes."), _prose_write("B.md", "58 passed.")]
    assert report_before_run_gate(history) is None


def test_a_pasted_runner_summary_is_a_report_too():
    """`58 passed in 2.0s` alone, with no prose around it: the hardened prose reader does NOT
    match it, so this isolates the pasted-summary reader. The first draft of this test said
    "Suite green: 58 passed." and BOTH readers matched, so a plant removing the summary reader
    left it green -- a test that cannot fail on the thing it names."""
    from makoto.substrate.claims import whole_suite_pass_claim
    assert not whole_suite_pass_claim("58 passed in 2.0s"), "the fixture must isolate one reader"
    assert report_before_run_gate([_prose_write("NOTES.md", "58 passed in 2.0s")]) is not None


def test_an_edit_reports_as_much_as_a_prose_write():
    assert report_before_run_gate(
        [_prose_write("HANDOFF.md", "The suite passes.", tool_name="Edit")]) is not None


# ---- the target firewall: prose is a report, code is data ------------------------------------

@pytest.mark.parametrize("path", ["tests/test_x.py", "plugin/makoto/kit.py", "data.json",
                                  "Makefile", "run.sh"])
def test_a_verdict_in_code_is_a_fixture_not_a_report(path):
    """This package's own tests carry `2 failed, 56 passed in 2.0s` as test data. A gate that
    fired on writing them would fire on writing itself -- measured, not supposed: the string
    below is the shape tests/test_unnamed_failure.py actually contains."""
    history = [_prose_write(path, 'RED_OUTPUT = "2 failed, 56 passed in 2.0s"')]
    assert report_before_run_gate(history) is None


@pytest.mark.parametrize("path", ["HANDOFF.md", "README.markdown", "notes.rst", "log.txt",
                                  "doc.adoc", "plan.org"])
def test_every_prose_extension_is_in_subject(path):
    assert report_before_run_gate([_prose_write(path, "The suite passes.")]) is not None, path


# ---- the guards the hardened prose reader supplies -------------------------------------------

def test_a_subset_claim_fails_open():
    """`substrate/claims.whole_suite_pass_claim`'s head-vs-modifier firewall: an honest partial
    claim is not a whole-suite report, and this gate inherits that rather than re-deciding it."""
    assert report_before_run_gate([_prose_write("HANDOFF.md", "The parser tests pass.")]) is None


def test_a_negated_claim_is_not_a_report():
    assert report_before_run_gate([_prose_write("HANDOFF.md", "The suite does not pass yet.")]) is None


def test_a_forward_framed_claim_is_not_a_report():
    assert report_before_run_gate(
        [_prose_write("HANDOFF.md", "The suite will pass once I fix this.")]) is None


def test_prose_with_no_verdict_at_all():
    assert report_before_run_gate([_prose_write("HANDOFF.md", "Work continues on the parser.")]) is None


# ---- the shape and the named bounds ----------------------------------------------------------

def test_a_pretooluse_row_wrote_nothing():
    row = _prose_write("HANDOFF.md", "The suite passes.")
    row["payload"]["hook_event_name"] = "PreToolUse"
    assert report_before_run_gate([row]) is None


def test_bash_is_not_a_report_channel_and_the_TARGET_gate_is_why():
    """The recall bound: a report written through a heredoc, `echo >` or `sed -i` is not seen.

    And the mechanism, because a plant found the docstring wrong about it. Admitting Bash to the
    tool allowlist does NOT make this fire: a Bash event carries no `file_path`, so the
    prose-target gate has already decided it. The allowlist is defense in depth over the same
    exclusion, not the thing doing the excluding -- measured below by admitting Bash and
    requiring silence anyway."""
    import makoto.checks.switch as mod
    ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
          "tool_input": {"command": "echo 'The suite passes.' > HANDOFF.md"},
          "tool_response": {"stdout": ""}}
    assert report_before_run_gate([{"payload": ev}]) is None
    original = mod._MUTATION_TOOLS
    try:
        mod._MUTATION_TOOLS = original | {"Bash"}
        assert not mod._reports_a_run_verdict(ev), \
            "the prose-target gate, not the tool allowlist, is what excludes a Bash report"
    finally:
        mod._MUTATION_TOOLS = original


def test_the_prose_failure_count_bound_is_real_and_named():
    """The green direction only, and the reason is that the prose failure-count lexicon belongs
    to gate.unnamed_failure, where it was measured. Pinned so the asymmetry stays a decision."""
    assert not _reports_a_run_verdict(
        _prose_write("HANDOFF.md", "3 tests failed.")["payload"])
