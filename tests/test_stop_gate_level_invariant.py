"""B1 — "every signal blocks or doesn't exist" extended to Stop gates, at RUNTIME.

Historically, `makoto/vocab.py`'s now-retired `load_prechecks()` enforced this invariant
for prechecks at LOAD TIME (`_ALLOWED_FIRE_LEVELS == {"error"}`, raising on any other
fire_level). That enforcement now lives in `tests/test_pre_tier_block_invariant.py` instead (see
`registry.load_precheck_catalog()`'s own docstring). Stop gates have no equivalent
load-time enforcement — Check carries no
`fire_level`/`blocking` field at all (only `may_block`, the structural discovery-eligibility
signal; by design that is NOT the same as "blocks" — the level lives on the `Finding` each gate's
predicate constructs when it actually fires).
tests/test_gate_shape.py::test_gate_dataclass_has_no_undeclared_shadow_state only pins the Check
dataclass SHAPE (no reintroduced 'blocking' field) — it never inspects what level a gate's
predicate emits when triggered. `gate.self_wired` (formerly stopchecks/stopcheck_self_wired.py) is the ONE
documented advisory exception (2026-07-05, DESIGN DECISION 6: an advisory-only partial-hook-strip
detector that must never block per the "advisory over blocking" standing policy). Nothing before
this test caught a SECOND silent advisory (or any other non-"error") gate being added later.

This test fires EVERY live gate discovered by `_live_gates()` through its real `.run(ctx)`
entry point — the exact call `run_stop_checks` makes — with a scenario proven (via each gate's own
existing sentinel tests / test_dispatch.py's behavioral pins, cited per-branch below) to make it
emit at least one Finding, then asserts the emitted level is "error" (the only blocking level,
makoto.vocab._ALLOWED_FIRE_LEVELS) UNLESS the gate id is in the explicit, named allowlist below.
A future gate that ships a silent advisory tier without updating the allowlist reddens here.
"""
from __future__ import annotations

import json
import os

from makoto.registry import _ADVISORY_ALLOWLIST, load_checks
from makoto.context import GateContext


def _live_gates() -> list:
    """The checks eligible to reach the Stop decision pipeline at all (formerly:
    load_stopchecks()'s GATE-export scan) -- Check.may_block=True."""
    return [c for c in load_checks(edge="Stop") if c.may_block]

def _ctx(**over):
    base = dict(text="", touched=frozenset(), empty=frozenset(), testrun_output="",
                cwd="", fs_exists=lambda p: False, fs_size=lambda p: None, fs_read=lambda p: None,
                history=())
    base.update(over)
    return GateContext(**base)


def _scenario_completion(tmp_path):
    # fires: tests/test_completion_governance.py::test_genuine_production_claims_still_fire
    return _ctx(text="I wrote config.yaml")


def _scenario_green_claim(tmp_path):
    # fires: tests/test_stale_pass_gate.py sibling test_gate_fires_green_claim_over_red_run
    return _ctx(text="All tests pass now.", testrun_output="=== 3 failed, 678 passed in 12.3s ===")


def _scenario_dropped(tmp_path):
    # fires: tests/test_gate_dropped.py::test_tp_count_drop
    return _ctx(text="I will add 3 helper functions to utils.py")


def _scenario_fabricated_action(tmp_path):
    # fires: tests/test_fabricated_action_gate.py::test_fires_when_no_tool_calls_this_turn
    return _ctx(text="I ran `pytest tests/ -q`.", history=[])


def _scenario_named_test(tmp_path):
    # fires: tests/test_dispatch.py::test_dispatch_named_test_gate_blocks_after_recorded_named_red
    row = {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                        "tool_input": {"command": "python -m pytest tests/ -q"},
                        "tool_response": {"stdout": "FAILED tests/x.py::test_foo - AssertionError\n"
                                                     "1 failed in 0.1s",
                                          "stderr": "", "exitCode": 1}}}
    return _ctx(text="Good news — test_foo passes now.", history=[row])


def _scenario_stale_pass(tmp_path):
    # fires: tests/test_stale_pass_gate.py::test_d_teeth_live_failing_node_plus_clean_green_claim_FIRES
    cache = tmp_path / ".pytest_cache" / "v" / "cache"
    cache.mkdir(parents=True)
    cache.joinpath("lastfailed").write_text(json.dumps({"tests/t.py::test_red": True}))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text("def test_red():\n    assert False\n")
    return _ctx(text="All tests pass now.", cwd=str(tmp_path))


def _scenario_liveness(tmp_path):
    # fires: tests/test_dispatch.py::test_dispatch_liveness_gate_blocks_on_illusory_code
    f = tmp_path / "dead.py"
    f.write_text("def fn():\n d = 1 + 1\n return 0\n")
    return _ctx(cwd=str(tmp_path), touched=frozenset({str(f)}),
                fs_read=lambda p: open(p, encoding="utf-8").read() if os.path.exists(p) else None)


def _scenario_hollow_test(tmp_path):
    # fires: tests/test_dispatch.py::test_dispatch_hollow_test_gate_blocks_on_hollow_test
    f = tmp_path / "test_a.py"
    f.write_text("def test_a():\n    x = compute()\n")
    return _ctx(cwd=str(tmp_path), touched=frozenset({str(f)}),
                fs_read=lambda p: open(p, encoding="utf-8").read() if os.path.exists(p) else None)


def _scenario_canon(tmp_path):
    # fires: tests/test_dispatch.py::test_dispatch_canon_gate_blocks_by_default
    row = {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                        "tool_input": {"command": "some-long-running-thing"},
                        "tool_response": {"interrupted": True}}}
    return _ctx(history=[row])


def _scenario_canon_fingerprints(tmp_path):
    # fires nosrc_destruct (BLOCK, robust-core): a destructive Bash command, no test-run-red, no
    # source edit at all -> NOT_edit_test_after_red ∧ NOT_source_edited ∧ destructive_command.
    row = {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                        "tool_input": {"command": "rm -rf /tmp/scratch"},
                        "tool_response": {"stdout": "", "stderr": "", "exitCode": 0}}}
    return _ctx(history=[row])


def _scenario_canon_fingerprints_advisory(tmp_path):
    # fires nogreen_weakened (ADVISE, soft atom): an Edit on a test file that degenerates a real
    # assertion into a tautology, with no green test run recorded.
    row = {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Edit",
                        "tool_input": {"file_path": "tests/test_x.py",
                                       "old_string": "assert x == 5",
                                       "new_string": "assert True"},
                        "tool_response": {}}}
    return _ctx(history=[row])


def _scenario_self_wired(tmp_path):
    # fires: tests/test_self_wired_check.py (partial strip: Stop entry missing)
    wired = json.dumps({"hooks": {
        "PreToolUse": [{"hooks": [{"command": "python3 -m makoto.dispatch"}]}],
        "PostToolUse": [{"hooks": [{"command": "python3 -m makoto.dispatch"}]}],
    }})
    return _ctx(fs_read=lambda p: wired if p == ".claude/settings.json" else None)


def _scenario_relative_path_citation(tmp_path):
    # fires: tests/test_relative_path_citation.py::test_gate_fires_finding_advisory_never_error
    return _ctx(text="see checks/hollowTest.py:146 for the detector")


def _scenario_plan_item_drift(tmp_path):
    # fires: tests/test_plan_items.py::test_drift_gate_advisory_lists_open_items
    return _ctx(open_plan_items=[{"commitment_key": "k", "label": "section:9.3", "description": "d"}])


def _scenario_claimed_running(tmp_path):
    # fires: tests/test_claimed_running_gate.py::test_fires_when_claim_has_no_grounding_evidence
    return _ctx(text="I started the server. It is now running on port 3000.", history=[])


def _scenario_claimed_shipped(tmp_path):
    # fires: tests/test_claimed_shipped_gate.py::test_gate_fires_on_bare_unbacked_claim
    return _ctx(text="I merged the PR.", history_all_agents=[])


# Every discovered gate id must have a firing scenario here — a new gate added to checks/
# without an entry below fails loudly (KeyError) rather than being silently skipped.
def _scenario_unexamined_wall(tmp_path):
    # fires on an epistemic "cannot" stated with NO act since the operator last spoke. The
    # transcript carries one genuine operator turn (the window boundary) and the history is
    # empty, so the inventory was never opened.
    import json as _json
    tp = tmp_path / "wall_transcript.jsonl"
    tp.write_text(_json.dumps({"message": {"role": "user", "content": "carry on"},
                               "timestamp": "2026-09-08T10:00:00Z"}) + "\n", encoding="utf-8")
    return _ctx(text="There is no way to tell whether the suite passes.",
                history=[], transcript_path=str(tp))


def _scenario_claimed_consent_absent(tmp_path):
    # fires on a claim citing the operator in a session whose transcript carries no genuine
    # operator turn at all. The transcript here holds one TOOL-RESULT-shaped user entry, which
    # `_is_genuine_user_turn` refuses -- so the oracle channel is empty and every attribution to
    # it is false, which is the whole firing condition.
    import json as _json
    tp = tmp_path / "transcript.jsonl"
    tp.write_text(_json.dumps({"type": "user", "message": {"role": "user", "content": "ok"},
                               "toolUseResult": {"stdout": ""},
                               "timestamp": "2026-09-08T10:00:00Z"}) + "\n", encoding="utf-8")
    return _ctx(text="You approved this, so I merged it.", transcript_path=str(tp))


def _scenario_unprobed_fanout(tmp_path):
    # fires: tests/test_obligation_gates.py::test_unprobed_fanout_fires_on_a_dispatch_with_no_read
    # A dispatch with no Read/Glob/Grep anywhere earlier in the session.
    row = {"payload": {"hook_event_name": "PreToolUse", "tool_name": "Task",
                       "tool_input": {"description": "go and refactor the parser"}}}
    return _ctx(history=[row])


def _scenario_unasked_plan(tmp_path):
    # fires: tests/test_obligation_gates.py::test_unasked_plan_fires_on_a_plan_with_no_question
    # A plan presented with no AskUserQuestion anywhere earlier in the session.
    row = {"payload": {"hook_event_name": "PreToolUse", "tool_name": "ExitPlanMode",
                       "tool_input": {"plan": "step 1, step 2"}}}
    return _ctx(history=[row])


def _bash_row(command, stdout="", tool_name="Bash"):
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": tool_name,
                        "tool_input": {"command": command},
                        "tool_response": {"stdout": stdout, "exitCode": 0}}}


def _scenario_unread_structure(tmp_path):
    # fires: tests/test_obligation_gates.py::test_unread_structure_fires_on_a_null_traversal
    return _ctx(history=[_bash_row("jq '.a.b' config.json", "null")])


def _scenario_unwitnessed_verifier(tmp_path):
    # fires: tests/test_obligation_gates.py::test_unwitnessed_verifier_fires_on_a_first_clean_run
    return _ctx(history=[_bash_row("pytest -q", "58 passed in 2.0s")])


def _scenario_unknown_ref_switch(tmp_path):
    # fires: tests/test_obligation_gates.py::test_unknown_ref_switch_fires_on_an_unprinted_ref
    return _ctx(history=[_bash_row("git checkout feature-x")])


def _scenario_unobserved_destruction(tmp_path):
    # fires: tests/test_obligation_gates.py::test_unobserved_destruction_fires_with_no_verifier
    return _ctx(history=[_bash_row("rm -rf build/")])


def _scenario_relaunched_unchanged(tmp_path):
    # fires: tests/test_obligation_gates.py::test_relaunched_unchanged_fires_on_the_second_launch
    row = {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Task",
                       "tool_input": {"description": "go"}, "tool_response": {}}}
    return _ctx(history=[row, row])


def _scenario_undischarged_waiver(tmp_path):
    # fires: tests/test_undischarged_waiver.py::test_fires_on_a_bare_lint_directive
    row = {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Edit",
                       "tool_input": {"file_path": "src/parser.py", "old_string": "a",
                                      "new_string": "value = parse(raw)  # noqa"},
                       "tool_response": {}}}
    return _ctx(history=[row])


def _scenario_unnamed_failure(tmp_path):
    # fires: tests/test_unnamed_failure.py::test_fires_on_a_count_with_no_name
    return _ctx(text="1 test failed; looking into it.",
                history=[_bash_row("python3 -m pytest -q",
                                   "tests/test_a.py::test_charge FAILED\n1 failed in 1.0s")])


def _scenario_report_before_run(tmp_path):
    # fires: tests/test_report_before_run.py::test_fires_on_a_report_with_no_run_before_it
    return _ctx(history=[{"payload": {"hook_event_name": "PostToolUse", "tool_name": "Write",
                                      "tool_input": {"file_path": "HANDOFF.md",
                                                     "content": "The suite passes."},
                                      "tool_response": {}}}])


def _scenario_unclaimed_unit(tmp_path):
    # fires: tests/test_unclaimed_unit.py::test_fires_on_a_unit_nothing_reaches
    return _ctx(history=[{"payload": {"hook_event_name": "PostToolUse", "tool_name": "Write",
                                      "tool_input": {"file_path": "src/helpers.py",
                                                     "content": "def helper(a):\n    return a + 1\n"},
                                      "tool_response": {}}}])


def _scenario_pasted_fix(tmp_path):
    # fires: tests/test_pasted_fix.py::test_fires_when_the_same_repair_reaches_a_second_file
    _REPAIR = ("if timeout is None:\n"
               "    timeout = DEFAULT_TIMEOUT\n"
               "if timeout < 0:\n"
               "    raise ValueError(timeout)\n")

    def row(path):
        return {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Edit",
                            "tool_input": {"file_path": path, "old_string": "pass",
                                           "new_string": _REPAIR},
                            "tool_response": {}}}
    return _ctx(history=[row("src/reader.py"), row("src/writer.py")])


_SCENARIOS = {
    "gate.unclaimed_unit": _scenario_unclaimed_unit,
    "gate.pasted_fix": _scenario_pasted_fix,
    "gate.report_before_run": _scenario_report_before_run,
    "gate.unnamed_failure": _scenario_unnamed_failure,
    "gate.undischarged_waiver": _scenario_undischarged_waiver,
    "gate.unread_structure": _scenario_unread_structure,
    "gate.unwitnessed_verifier": _scenario_unwitnessed_verifier,
    "gate.unknown_ref_switch": _scenario_unknown_ref_switch,
    "gate.unobserved_destruction": _scenario_unobserved_destruction,
    "gate.relaunched_unchanged": _scenario_relaunched_unchanged,
    "gate.unprobed_fanout": _scenario_unprobed_fanout,
    "gate.unasked_plan": _scenario_unasked_plan,
    "gate.claimed_consent_absent": _scenario_claimed_consent_absent,
    "gate.unexamined_wall": _scenario_unexamined_wall,
    "gate.completion": _scenario_completion,
    "gate.green_claim": _scenario_green_claim,
    "gate.dropped": _scenario_dropped,
    "gate.fabricated_action": _scenario_fabricated_action,
    "gate.named_test": _scenario_named_test,
    "gate.stale_pass": _scenario_stale_pass,
    "gate.liveness": _scenario_liveness,
    "gate.hollow_test": _scenario_hollow_test,
    "gate.canon": _scenario_canon,
    "gate.canon_fingerprints": _scenario_canon_fingerprints,
    "gate.canon_fingerprints_advisory": _scenario_canon_fingerprints_advisory,
    "gate.self_wired": _scenario_self_wired,
    "gate.relative_path_citation": _scenario_relative_path_citation,
    "gate.plan_item_drift": _scenario_plan_item_drift,
    "gate.claimed_running": _scenario_claimed_running,
    "gate.claimed_shipped": _scenario_claimed_shipped,
}


def _findings_for(gate, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)   # per-gate scratch dir (some scenarios write files)
    ctx = _SCENARIOS[gate.id](tmp_path)
    result = gate.run(ctx)
    if result is None:
        return []
    if isinstance(result, (list, tuple)):
        return list(result)
    return [result]


def test_every_history_eating_gate_fails_open_on_malformed_rows():
    """ONE home for what four new test modules were each restating in 2026-09-18.

    `gate.undischarged_waiver`, `gate.unnamed_failure`, `gate.report_before_run` and
    `gate.unclaimed_unit` each shipped a `test_an_undecodable_row_...` asserting the same thing
    about its own gate. The claim is not per-gate -- a malformed event is no evidence for ANY of
    them, and a raise here is a check-evaluation fault that fails the call open without being
    checked (dispatch records it in dispatch_errors.jsonl). So it is asserted over the whole set,
    where a gate added without the tolerance reddens, rather than four times where only the four
    are covered.

    The rows below are every shape a decoder can meet: a non-row object, None, a bare string, an
    empty dict, and a dict whose payload is not a mapping.
    """
    rows = [object(), None, "not a row", {}, {"payload": "nope"}, {"payload": {}}]
    for gate in _live_gates():
        if "history" not in (gate.eats or frozenset()):
            continue
        ctx = _ctx(history=rows)
        try:
            result = gate.run(ctx)
        except Exception as exc:                       # pragma: no cover - the failure path
            raise AssertionError(
                f"{gate.id} raised on a malformed history row ({exc!r}); a Stop gate must treat "
                f"an undecodable event as no evidence, never as a fault") from exc
        findings = result if isinstance(result, list) else ([result] if result else [])
        assert not findings, (
            f"{gate.id} produced {len(findings)} finding(s) from rows that carry no evidence at "
            f"all: {[f.pattern_id for f in findings]}")


def test_every_scenario_covers_a_discovered_gate():
    """The scenario map's keys must equal exactly the discovered gate ids — neither stale (a
    removed gate leaves a dead scenario) nor missing (a new gate ships without one)."""
    discovered = {g.id for g in _live_gates()}
    assert set(_SCENARIOS) == discovered


def test_every_gate_scenario_actually_fires(tmp_path):
    """Sanity precondition for the level check below: each scenario must produce >=1 Finding, or
    the level assertion would be vacuously true and this whole test would be worthless."""
    silent = [g.id for g in _live_gates() if not _findings_for(g, tmp_path / g.id)]
    assert not silent, f"scenario(s) did not fire (fixture drift?): {silent}"


def _violation(gate_id: str, level: str):
    """THE invariant, as a callable, so its teeth test can APPLY it instead of restating it.

    The teeth test below used to spell out `(id not in allowlist) and (level != "error")` in its
    own words. That proves nothing about the rule that ships: the two can be edited apart and
    the teeth test goes on passing over a rule that has stopped discriminating. Both callers run
    this function now.
    """
    if gate_id in _ADVISORY_ALLOWLIST:
        if level == "error":
            return (gate_id, level, "allowlisted gate emitted 'error' — allowlist entry is "
                                    "stale, remove it")
        return None
    if level != "error":
        return (gate_id, level, "non-blocking level on a non-allowlisted gate — either this is "
                                "a bug, or the gate needs an explicit, named, "
                                "DESIGN-DECISION-cited allowlist entry")
    return None


def test_every_fired_gate_is_blocking_level_unless_named_advisory(tmp_path):
    """The runtime invariant: every live Stop gate's emitted Finding.level is "error" (the sole
    blocking level, makoto.vocab._ALLOWED_FIRE_LEVELS) UNLESS its id is in _ADVISORY_ALLOWLIST.
    A future gate that silently ships a second advisory-tier exception reddens THIS test, not just
    a shape/dataclass pin."""
    violations = []
    for g in _live_gates():
        for finding in _findings_for(g, tmp_path / g.id):
            violation = _violation(g.id, finding.level)
            if violation:
                violations.append(violation)
    assert not violations, violations


def test_TEETH_allowlist_check_catches_an_unnamed_advisory_gate():
    """Planted-violation teeth (mirrors tests/test_gate_shape.py's TEETH_* style): a hypothetical
    gate id NOT in the allowlist that emits level="advisory" must be flagged by the same logic
    the real test above applies, proving the check has discriminating power rather than always
    passing vacuously."""
    assert _ADVISORY_ALLOWLIST, "the allowlist is empty; both halves below would be vacuous"
    # An id NOT on the allowlist emitting a non-blocking level: the defect the rule exists for.
    assert _violation("gate.not_on_the_allowlist", "advisory") is not None, (
        "the shipped invariant does not report an unnamed gate shipping an advisory level")
    # ...and a named exception at the same level must NOT be reported, or the rule reports
    # everything and its silence above means nothing.
    named = sorted(_ADVISORY_ALLOWLIST)[0]
    assert _violation(named, "advisory") is None, (
        f"the shipped invariant reports {named}, which is on the allowlist precisely so it may "
        f"ship an advisory level")
    # The other direction the rule also owns: an allowlisted gate that has started blocking.
    assert _violation(named, "error") is not None, (
        f"a stale allowlist entry -- {named} now emitting 'error' -- goes unreported")
