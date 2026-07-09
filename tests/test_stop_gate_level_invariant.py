"""B1 — "every signal blocks or doesn't exist" extended to Stop gates, at RUNTIME.

makoto/schema.py's load_prechecks() enforces this invariant for prechecks at LOAD TIME:
_ALLOWED_FIRE_LEVELS == {"error"} and the loader raises on any other fire_level (see
schema.py:77-81). Stop gates have no equivalent load-time enforcement — StopCheck carries no
`fire_level`/`blocking` field at all (by design: discovered <=> live <=> blocking); the level lives
on the `Finding` each gate's predicate constructs when it actually fires.
tests/test_gate_shape.py::test_gate_dataclass_has_no_shadow_tier_field only pins the StopCheck
dataclass SHAPE (no reintroduced 'blocking' field) — it never inspects what level a gate's
predicate emits when triggered. `gate.self_wired` (stopchecks/stopcheck_self_wired.py) is the ONE
documented advisory exception (2026-07-05, FABLE DECISION 6: an advisory-only partial-hook-strip
detector that must never block per the "advisory over blocking" standing policy). Nothing before
this test caught a SECOND silent advisory (or any other non-"error") gate being added later.

This test fires EVERY live gate discovered by `load_stopchecks()` through its real `.run(ctx)`
entry point — the exact call `run_stop_checks` makes — with a scenario proven (via each gate's own
existing sentinel tests / test_dispatch.py's behavioral pins, cited per-branch below) to make it
emit at least one Finding, then asserts the emitted level is "error" (the only blocking level,
makoto.core.schema._ALLOWED_FIRE_LEVELS) UNLESS the gate id is in the explicit, named allowlist below.
A future gate that ships a silent advisory tier without updating the allowlist reddens here.
"""
from __future__ import annotations

import json
import os

from makoto.substrate._loader import load_stopchecks
from makoto.substrate._shared import GateContext

# The ONLY documented exception to "every Stop-gate finding blocks" (2026-07-05, FABLE DECISION 6):
# gate.self_wired ships at level="advisory" so a partial hook-wiring strip is recorded to the audit
# trail without ever blocking a turn (stopchecks/stopcheck_self_wired.py's own docstring; behavioral
# pin: tests/test_dispatch.py::test_dispatch_self_wired_gate_never_blocks_even_when_it_fires).
# Adding a gate id here must cite its own FABLE DECISION the same way.
#
# gate.canon_fingerprints_advisory (SPEC-5 Task 9, FABLE DECISION 26) is the second: 13 of the 17
# ported canon session fingerprints rest on a soft/claim atom the gold-oracle finding doc's robust
# core does not name, or are among that doc's explicitly-named WORST DISQUALIFIED fingerprints —
# SPEC-5's own total-retention rule keeps them in the catalog, evaluated and recorded, but never
# blocking. Its sibling gate.canon_fingerprints (the 4 robust-core, blocking-capable fingerprints)
# is intentionally NOT here — it always emits level="error" (see canonFingerprints.py).
_ADVISORY_ALLOWLIST = frozenset({"gate.self_wired", "gate.canon_fingerprints_advisory"})  # FD6, FD26


def _ctx(**over):
    base = dict(text="", touched=frozenset(), empty=frozenset(), opens=(), testrun_output="",
                cwd="", fs_exists=lambda p: False, fs_size=lambda p: None, fs_read=lambda p: None,
                history=())
    base.update(over)
    return GateContext(**base)


def _scenario_completion(tmp_path):
    # fires: tests/test_completion_governance.py::test_genuine_production_claims_still_fire
    return _ctx(text="I wrote config.yaml")


def _scenario_advance(tmp_path):
    # fires: tests/test_advance_signal.py::test_genuinely_dropped_commitment_still_fires
    return _ctx(text="Everything is wired up now.", opens=[{"location": "src/missing.py"}])


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


def _scenario_contract_order(tmp_path):
    # fires: makoto.checks.contractOrder's Stop remainder guard -- a declared node still open.
    from makoto.substrate._planNode import Plan
    plan = Plan()
    plan.add_node("Write", "auth.py", "/repo/auth.py", id="n1")
    return _ctx(plan=plan)


def _scenario_self_wired(tmp_path):
    # fires: tests/test_stopcheck_self_wired.py (partial strip: Stop entry missing)
    wired = json.dumps({"hooks": {
        "PreToolUse": [{"hooks": [{"command": "python3 -m makoto._dispatch"}]}],
        "PostToolUse": [{"hooks": [{"command": "python3 -m makoto._dispatch"}]}],
    }})
    return _ctx(fs_read=lambda p: wired if p == ".claude/settings.json" else None)


# Every discovered gate id must have a firing scenario here — a new gate added to checks/
# without an entry below fails loudly (KeyError) rather than being silently skipped.
_SCENARIOS = {
    "gate.completion": _scenario_completion,
    "gate.advance": _scenario_advance,
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
    "gate.contract_order": _scenario_contract_order,
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


def test_every_scenario_covers_a_discovered_gate():
    """The scenario map's keys must equal exactly the discovered gate ids — neither stale (a
    removed gate leaves a dead scenario) nor missing (a new gate ships without one)."""
    discovered = {g.id for g in load_stopchecks()}
    assert set(_SCENARIOS) == discovered


def test_every_gate_scenario_actually_fires(tmp_path):
    """Sanity precondition for the level check below: each scenario must produce >=1 Finding, or
    the level assertion would be vacuously true and this whole test would be worthless."""
    silent = [g.id for g in load_stopchecks() if not _findings_for(g, tmp_path / g.id)]
    assert not silent, f"scenario(s) did not fire (fixture drift?): {silent}"


def test_every_fired_gate_is_blocking_level_unless_named_advisory(tmp_path):
    """The runtime invariant: every live Stop gate's emitted Finding.level is "error" (the sole
    blocking level, makoto.core.schema._ALLOWED_FIRE_LEVELS) UNLESS its id is in _ADVISORY_ALLOWLIST.
    A future gate that silently ships a second advisory-tier exception reddens THIS test, not just
    a shape/dataclass pin."""
    violations = []
    for g in load_stopchecks():
        for finding in _findings_for(g, tmp_path / g.id):
            if g.id in _ADVISORY_ALLOWLIST:
                if finding.level == "error":
                    violations.append((g.id, finding.level, "allowlisted gate emitted 'error' — "
                                        "allowlist entry is stale, remove it"))
            elif finding.level != "error":
                violations.append((g.id, finding.level, "non-blocking level on a non-allowlisted "
                                    "gate — either this is a bug, or the gate needs an explicit, "
                                    "named, FABLE-DECISION-cited allowlist entry"))
    assert not violations, violations


def test_TEETH_allowlist_check_catches_an_unnamed_advisory_gate():
    """Planted-violation teeth (mirrors tests/test_gate_shape.py's TEETH_* style): a hypothetical
    gate id NOT in the allowlist that emits level="advisory" must be flagged by the same logic
    the real test above applies, proving the check has discriminating power rather than always
    passing vacuously."""
    fake_id, fake_level = "gate.not_on_the_allowlist", "advisory"
    is_violation = (fake_id not in _ADVISORY_ALLOWLIST) and (fake_level != "error")
    assert is_violation
    # and the real allowlisted exception must NOT be flagged as a violation:
    real_id, real_level = "gate.self_wired", "advisory"
    is_violation_real = (real_id not in _ADVISORY_ALLOWLIST) and (real_level != "error")
    assert not is_violation_real
