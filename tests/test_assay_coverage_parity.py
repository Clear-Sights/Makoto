"""SPEC-5 Task 10, Steps 1-2: the Assay -> merged-Makoto coverage-parity map.

Retiring `assay/` (Task 10 Step 3, NOT this file's job -- that needs its own separate
owner confirmation once this map is green, per FABLE DECISION 25) is gated on every one of
Assay's 184 tests having a DOCUMENTED destination in merged Makoto -- "zero coverage lost."
"Documented" does not mean "silently absorbed": three classes of outcome are equally
legitimate and must be told apart, one per Assay test FILE (`assay/tests/*.py`):

  * PORTED    -- the file's coverage has a real, live, passing home under `makoto/tests/`.
  * PARTIAL   -- some of the file's arms ported; the rest are one of the other two outcomes
                 for a documented reason (mixed files, e.g. a wiring-test file covering both
                 a ported detector and an unported one).
  * EXCLUDED  -- ruled out of the merge's scope by name, citing the real decision/entry that
                 ruled it out (FABLE DECISION 26, or SPEC-5's own original cut-list for the
                 pieces that were never in scope to begin with -- Lever-bound telemetry).
  * PENDING_STEP_3 -- genuinely belongs to Task 10 Step 3 itself (install/hook-wiring
                 rewiring once Makoto becomes the sole installed faculty), not decidable
                 before that step, and Step 3 is explicitly out of this dispatcher's scope.

This is the map FABLE DECISION 26 requires: `content_breach`/`stale_provenance`/`drift` (and
the `grammar_instances`/10-unported-canon-fingerprint gaps found alongside them) must show up
here as an explicit EXCLUDED line, not a silent absence.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ASSAY_TESTS = REPO_ROOT / "assay" / "tests"
if not (REPO_ROOT / "EXECUTION_PLAN.md").exists():
    # Standalone makoto checkout (no Skill-lab-V5 monorepo siblings): the parity map's source
    # documents don't exist here, so the whole module is honestly out of scope — the same
    # sibling-absent skip discipline test_hollow_test_fp.py's assay/ventura corpus tests use,
    # raised to module level because these reads happen at import time.
    import pytest
    pytest.skip("Skill-lab-V5 monorepo docs not present (standalone makoto checkout)",
                allow_module_level=True)
EXECUTION_PLAN_TEXT = (REPO_ROOT / "EXECUTION_PLAN.md").read_text()
DEFERRED_TEXT = (REPO_ROOT / "DEFERRED.md").read_text()
SPEC_5_TEXT = (REPO_ROOT / "SPEC-5-MAKOTO-ABSORBS-ASSAY.md").read_text()
_ALL_DOCS = (EXECUTION_PLAN_TEXT, DEFERRED_TEXT, SPEC_5_TEXT)

# Each citation below is a REAL substring verified present in one of _ALL_DOCS (checked by
# test_every_excluded_entry_cites_a_real_documented_decision) -- not a paraphrase.
_CUTLIST = "EXPLICIT CUT LIST — pieces that do NOT merge (they belong to Lever, a later phase)"
_FD26 = "FABLE DECISION 26"
# test_ledger.py/test_tamper_escalation.py exercise the SAME anchor/hash-chain substrate FD26's
# own text names as the reason content_breach/drift don't port -- cite that exact clause.
_LEDGER_GAP = "a content+location fingerprint stream"

# One entry per real `assay/tests/*.py` file (asserted exhaustive below).
PARITY: dict = {
    "test_forbidden_location.py": {
        "status": "PORTED",
        "destinations": ["makoto/tests/predicates/test_forbidden_location.py"],
        "note": "Task 5 -- straight port, including the MultiEdit/NotebookEdit regression case.",
    },
    "test_stale_establisher.py": {
        "status": "PORTED",
        "destinations": ["makoto/tests/test_stale_establisher.py"],
        "note": "Task 7.",
    },
    "test_content_breach.py": {
        "status": "EXCLUDED",
        "decision": _FD26,
        "note": "No live write-side data source in Makoto (Assay's engine.anchor_call has no analog).",
    },
    "test_stale_provenance.py": {
        "status": "EXCLUDED",
        "decision": _FD26,
        "note": "Its AssayAnchor tool binding is confirmed-inert, not real anywhere including in Assay.",
    },
    "test_binding.py": {
        "status": "EXCLUDED",
        "decision": _CUTLIST,
        "note": "Historia surfacing write-side -- SPEC-5's original cut list, Lever-bound.",
    },
    "test_surface.py": {
        "status": "EXCLUDED",
        "decision": _CUTLIST,
        "note": "Historia surfacing read-side -- SPEC-5's original cut list, Lever-bound.",
    },
    "test_liveness.py": {
        "status": "EXCLUDED",
        "decision": _CUTLIST,
        "note": "Silent-death liveness advisory -- SPEC-5's original cut list, Lever-bound.",
    },
    "test_token_cost.py": {
        "status": "EXCLUDED",
        "decision": _CUTLIST,
        "note": "Token/cost recording -- SPEC-5's original cut list, Lever-bound.",
    },
    "test_ledger.py": {
        "status": "EXCLUDED",
        "decision": _LEDGER_GAP,
        "note": ("Concurrent-append lock + verify_chain over Assay's own hash-chained JSONL "
                 "store -- the same substrate gap FABLE DECISION 26 ruled on for Task 6; "
                 "makoto/ledger.py is a different, simpler substrate with no analog."),
    },
    "test_tamper_escalation.py": {
        "status": "EXCLUDED",
        "decision": _LEDGER_GAP,
        "note": "Tamper classification built on kernel.ledger.verify_chain_classified -- same gap as test_ledger.py.",
    },
    "test_hook_install_wiring.py": {
        "status": "PENDING_STEP_3",
        "note": ("Assay's own install()/with_hooks() SubagentStop wiring -- only meaningful once "
                 "Makoto is the sole installed faculty (Task 10 Step 3), out of this dispatcher's scope."),
    },
    "test_catalog_wiring.py": {
        "status": "PARTIAL",
        "destinations": [
            "makoto/tests/predicates/test_forbidden_location.py",
            "makoto/tests/test_dispatch_posture_integration.py",
            "makoto/tests/test_posture_wire.py",
        ],
        "decision": _FD26,
        "note": ("forbidden_location wiring + the posture floor (session-scoping, sacred "
                 "user-stop, silent off-switch, loose softening) ported; the malformed_call/"
                 "drift/stuck_sequence wiring arms are excluded (grammar_instances has no "
                 "Makoto grammar-engine analog, DEFERRED.md; drift is FD26-excluded)."),
    },
    "test_engine_coverage.py": {
        "status": "PARTIAL",
        "destinations": [
            "makoto/tests/test_plan_store.py",
            "makoto/tests/test_plan_node.py",
            "makoto/tests/test_dispatch_posture_integration.py",
            "makoto/tests/test_dispatch.py",
        ],
        "note": ("declare_from_artifact fail-matrix + declare()'s falsifiability gate -> "
                 "test_plan_store.py/test_plan_node.py (Task 7); POST BLOCK->ADVISE clamp -> "
                 "test_dispatch_posture_integration.py (Task 8); generic wrong-shaped-payload "
                 "dispatch tolerance was already covered pre-merge by Makoto's own test_dispatch.py."),
    },
    "test_io_paths.py": {
        "status": "PARTIAL",
        "destinations": ["makoto/tests/test_dispatch.py", "makoto/tests/predicates/test_forbidden_location.py"],
        "note": ("Black-box subprocess-wire tests over Assay's own hook_bridge entry point -- "
                 "Makoto already has its own equivalent subprocess-level coverage pre-merge "
                 "(test_dispatch.py); the one real regression this file guards is content-identical "
                 "to test_forbidden_location.py's, already ported."),
    },
    "test_io_frozen.py": {
        "status": "PARTIAL",
        "destinations": ["makoto/tests/test_dispatch.py", "makoto/tests/predicates/test_forbidden_location.py"],
        "note": ("Byte-frozen golden-file replay of the same 16 wire cases as test_io_paths.py, "
                 "plus the MultiEdit/NotebookEdit forbidden_location fix -- same disposition."),
    },
}


def test_assay_test_file_inventory_is_current():
    """PARITY's keys must exactly match the real assay/tests/*.py file set -- a new or removed
    Assay test file must update this map, not silently drift from it."""
    live = {p.name for p in ASSAY_TESTS.glob("test_*.py")}
    assert set(PARITY) == live, (
        f"parity map out of sync with assay/tests/: missing={live - set(PARITY)} "
        f"stale={set(PARITY) - live}")


def test_assay_suite_is_184_tests_the_documented_floor():
    """Re-collected LIVE (not hand-counted) so a change to Assay's own suite size is caught
    here before Task 11's gate assumes 184 is still the floor."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(ASSAY_TESTS), "--collect-only", "-q"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    m = re.search(r"(\d+) tests? collected", result.stdout)
    assert m, result.stdout
    assert int(m.group(1)) == 184


def test_every_ported_or_partial_destination_exists_and_has_tests():
    for name, entry in PARITY.items():
        if entry["status"] not in ("PORTED", "PARTIAL"):
            continue
        for dest in entry["destinations"]:
            p = REPO_ROOT / dest
            assert p.exists(), f"{name}: claimed destination {dest} does not exist"
            assert re.search(r"^\s*def test_", p.read_text(), re.M), (
                f"{name}: claimed destination {dest} has no test functions")


def test_every_excluded_entry_cites_a_real_documented_decision():
    for name, entry in PARITY.items():
        if entry["status"] != "EXCLUDED" and "decision" not in entry:
            continue
        cite = entry.get("decision")
        if cite is None:
            continue
        assert any(cite in doc for doc in _ALL_DOCS), (
            f"{name}: cited decision {cite!r} not found in EXECUTION_PLAN.md, DEFERRED.md, "
            f"or SPEC-5-MAKOTO-ABSORBS-ASSAY.md")


def test_fable_decision_26_is_real():
    """The specific decision this map exists to make explicit (not a silent absence)."""
    assert _FD26 in EXECUTION_PLAN_TEXT


def test_every_file_has_a_recognized_status():
    allowed = {"PORTED", "PARTIAL", "EXCLUDED", "PENDING_STEP_3"}
    for name, entry in PARITY.items():
        assert entry["status"] in allowed, f"{name}: unrecognized status {entry['status']!r}"
