"""The Stop-gate catalog's SHAPE is itself a word makoto emits about its own design — so it must be
MATERIAL, not illusory. This test pins the design (the gate-related file subset, function counts,
exports, the Check schema, the shared/named-gate split, the house style; the layering firewall
now lives in tests/test_import_direction.py — the pipeline file order IS the firewall)
AND proves each shape predicate has TEETH: a `test_TEETH_*` feeds it a planted violation and asserts
it goes red. The single source for "the design" is the EXPECTED_* declarations below — change the
package <=> change these <=> the test moves with it (a re-checkable artifact, not a comment).

SPEC-5 Task 4 (2026-07-07): the gate catalog moved from its own `makoto/stopchecks/` package (one
file per adapter/engine/harness, `stopcheck_*.py` prefix) into the shared flat `makoto/checks/`
package (SPEC-5 Task 2's home for every check, prechecks included) with descriptive names and each
adapter merged with its own engine into one file. `makoto/stopchecks/__init__.py` briefly survived
as a thin compat shim (`load_stopchecks()` re-exported, still memoized); that shim was removed
2026-07-09 (no backwards-compat shims policy). Then, 2026-07-10, `load_stopchecks()`/`GATE`/
`StopCheck` themselves were retired entirely: every gate module now expresses its Stop-edge
surface as a plain `CHECK` (or, for `contractOrder.py`'s dual Pre+Stop surface, an `EXTRA_CHECKS`
entry) discovered by the SAME unified `checks._loader.load_checks(edge="Stop")` every Pre-tier
check already used, with a new `Check.may_block` field marking exactly the checks that used to
export a `GATE` -- the structural "reaches the decision pipeline at all" signal, independent of
`.posture`/`.level` (see `_loader.py`'s `Check.may_block` docstring and `dispatch.py`'s
`_blocking_gate_ids()`). This test's GATES_DIR and every design declaration below point at
`checks/`. Because `checks/` also holds every precheck, `forbiddenLocation`, and the completeness
check itself, the file-shape assertion is a SUBSET check (the 11 named gates + 3 shared/harness
files must be present), not an exact-set equality over the whole directory the way the old
single-purpose `stopchecks/` package allowed.
"""
from __future__ import annotations
import ast
import dataclasses
import importlib
from pathlib import Path

from makoto.registry import Check, load_checks
from makoto.context import GateContext


def _live_gates() -> list:
    """The checks eligible to reach the Stop decision pipeline at all (formerly: discovered via
    load_stopchecks()'s GATE-export scan) -- Check.may_block=True, not every Stop-edge CHECK
    (staleEstablisher/undeclaredFalsifiable are Stop-edge but structurally excluded, may_block
    default False)."""
    return sorted(
        (c for c in load_checks(edge="Stop") if c.may_block),
        key=lambda c: c.id,
    )

GATES_DIR = Path(__file__).resolve().parent.parent / "plugin" / "makoto" / "checks"

# ---- the declared design (single source; the package must MATCH it) --------------------------
# The 11 named Stop-gate modules — each is its adapter AND its own engine merged into one file
# (SPEC-5 Task 4 folded what used to be a separate `stopcheck_X.py` + `X.py` engine pair together).
GATE_MODULE_STEMS = {
    "claimedProduceAbsent", "undischargedCommitment", "falseGreenClaim", "silentlyDroppedCommitment",
    "fabricatedToolAction", "namedTestTeeth", "stalePytestCache",
    "deadPureStatement",    # liveness gate: adapter + its own AST analyzer engine, one file
    "selfWiredCheck",       # the ONE advisory-tier exception to "discovered<=>live<=>blocking"
                            # (2026-07-05, DESIGN DECISION, self-defense-asymmetry-followup mitigation)
                            # — partial-strip detection of makoto's own settings.json hook wiring.
    "hollowTest",           # hollow_test gate: adapter + its own AST analyzer engine, one file
    "canonTimeoutRecur",    # canon gate: adapter + its own pure engine (canon.timeout/canon.recur)
    "canonFingerprints",           # SPEC-5 Task 9: BLOCK-tier half of the 17 canon fingerprints
    "canonFingerprintsAdvisory",   # SPEC-5 Task 9: ADVISE-tier half (shares _canonAtoms.py)
    "contractOrder",        # SPEC-5 (Makoto absorbs Assay): the plan's Stop remainder guard.
                             # staleEstablisher.py is its DETECTIVE/advisory sibling but is
                             # DELIBERATELY NOT a discovered GATE (no GATE export) -- it is
                             # invoked directly by run_stop_checks so its finding can never enter
                             # _blocking_gate_ids(), rather than needing a cited DESIGN-DECISION
                             # _ADVISORY_ALLOWLIST entry (test_stop_gate_level_invariant.py) this
                             # worker has no standing to mint.
    "relativePathCitation", # 2026-07-09: advisory-only, flags a chat response citing a non-
                             # absolute (unclickable) path. Discovered normally, like selfWiredCheck.
    "planItemDrift",        # 2026-07-09: advisory-only reminder of open plan/task-labeled
                             # commitments ("§9.3", "Task #19") sourced from chat prose by
                             # session/planItems.py -- see that module for why this can't reuse
                             # session/commitments.py's file-path-only sourcing.
    "claimedRunningAbsent", # 2026-07-23: an agnostic (gate.canon-sense) claimed-running-but-
                             # nothing-runs gate -- claim vs this session's own recorded Bash
                             # evidence, mirroring claimedProduceAbsent's claim-vs-ledger shape.
    "runIntentUnfulfilled", # 2026-07-23: claimedRunningAbsent's forward-looking sibling -- a
                             # first-person run-intent PROMISE ("I'll run the tests") left with no
                             # Bash evidence anywhere in history by the next turn. Stateless
                             # (no new persistence): the one-turn grace period falls out of
                             # `history` structurally never containing the row for the Stop
                             # currently being evaluated (see the module's own docstring).
    "claimedShippedAbsent", # completed remote mutation claim checked against successful Bash
                             # git-push and closed-set GitHub mutation evidence across all agents.
}
GATE_MODULE_FILES = {f"{stem}.py" for stem in GATE_MODULE_STEMS}
# the shared substrate (GateContext + common predicates) + the two test-only FP/soundness
# harnesses (never imported by a gate module itself — only by their own battery tests) that travel
# with the gate catalog but are not gates. _canonAtoms.py is the same kind of shared substrate,
# scoped to the two canonFingerprints* gates (SPEC-5 Task 9).
EXPECTED_SHARED_FILES = set()  # 2026-07-09: all former checks/ plumbing moved to substrate/
EXPECTED_GATE_FILES = GATE_MODULE_FILES | EXPECTED_SHARED_FILES     # 14 files, the gate subset of checks/
EXPECTED_LIVE_GATE_IDS = {"gate.completion", "gate.advance", "gate.green_claim", "gate.dropped",
                          "gate.fabricated_action", "gate.named_test", "gate.stale_pass", "gate.liveness",
                          "gate.self_wired", "gate.hollow_test", "gate.canon",
                          "gate.canon_fingerprints", "gate.canon_fingerprints_advisory",
                          "gate.contract_order",
                          "gate.relative_path_citation", "gate.plan_item_drift",
                          "gate.claimed_running", "gate.run_promised", "gate.claimed_shipped"}
EXPECTED_GATE_FIELDS = {"id", "applies_at", "posture", "run", "may_block",
                        "keywords", "retry_hint", "description", "predicate_module",
                        "layer", "eats", "tests"}   # "object" | "meta" -- see Check's own docstring; only
                                   # content.self_mute_guard / gate.self_wired are "meta" today
EXPECTED_CONTEXT_FIELDS = {"text", "touched", "empty", "opens", "testrun_output",
                           "cwd", "fs_exists", "fs_size", "fs_read", "history",
                           "permission_mode", "agent_id", "agent_type", "plan",
                           "session_id", "transcript_path", "state_root",
                           "open_plan_items",   # Task 2 slice 5 / 2026-07-09 planItemDrift
                           "history_all_agents"}   # 2026-07-23: gate.claimed_running's
                           # cross-agent-pooled Bash evidence twin of `history` (see GateContext's
                           # own field doc)
EXPECTED_FUNCTION_COUNTS = {                               # top-level def count per module, verified
    "claimedProduceAbsent.py": 2,
    "undischargedCommitment.py": 7,
    "falseGreenClaim.py": 1,
    "silentlyDroppedCommitment.py": 6,
    "fabricatedToolAction.py": 3,
    "namedTestTeeth.py": 7,                                # 6->7, 2026-07-09: recorded_failed_names/
                                                            # recorded_passed_names now share one
                                                            # extracted _recorded_names helper
    "stalePytestCache.py": 1,
    "deadPureStatement.py": 15,                            # engine + adapter merged (_run lives here);
                                                            # 19->15, 2026-07-09: _scratch_roots/_under/
                                                            # _is_scratch/_read extracted to _stdlib_ast_helpers.py
    "selfWiredCheck.py": 3,                                # 3->2, 2026-07-09: _entry_dispatches_to_makoto
                                                            # hoisted to substrate/wiring.py (shared with
                                                            # install.py -- the refactor the module's own
                                                            # note asked for). 2->3, 2026-07-22:
                                                            # _default_plugin_fs_read added (two-source
                                                            # wiring check, plugin manifest fallback)
    "hollowTest.py": 30,                                   # engine + adapter merged (_run lives here);
                                                            # 35->30, 2026-07-09: _callee_chain/_scratch_roots/
                                                            # _under/_is_scratch/_read extracted to
                                                            # _stdlib_ast_helpers.py
    "canonTimeoutRecur.py": 17,                            # engine + adapter merged (canon_gate lives here);
                                                            # 15->17, 2026-08-16 (#17 port): _pairing_input
                                                            # (dunder-insensitive Pre<->Post pairing identity)
                                                            # + _release_clause (per-primitive release.operator
                                                            # affordance, generated from the id)
    "canonFingerprints.py": 1,                             # thin adapter; atoms/decode live in _canonAtoms.py
    "canonFingerprintsAdvisory.py": 1,                     # thin adapter; atoms/decode live in _canonAtoms.py
    "contractOrder.py": 5,
    "relativePathCitation.py": 4,
    "planItemDrift.py": 1,
    "claimedRunningAbsent.py": 4,
    "runIntentUnfulfilled.py": 4,
    "claimedShippedAbsent.py": 5,
}
# Stage 2 seam 7: the gate-side import firewall (the former ALLOWED_IMPORT_ROOTS curated
# allowlist + sibling-gate scan) now lives in tests/test_import_direction.py — "the layer
# firewall becomes the file order": every makoto.* import must point strictly earlier in the
# pipeline-ordered layout, named gates may never import a sibling gate, and their reach into
# state/ stays narrowed to the ledger/citations read surfaces.


# ---- pure shape predicates (each is fed a planted violation by a test_TEETH_* below) ---------
def _def_count(src: str) -> int:
    return sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.parse(src).body)


def _leads_with_future_import(src: str) -> bool:
    """True if the future-annotations import is the file's first statement, or its first
    statement after a leading module docstring (SPEC-5 Task 4 merged each gate's own engine
    docstring into the adapter file, so a leading docstring is now legitimate house style,
    not a violation — the future-import must still come immediately after it)."""
    body = ast.parse(src).body
    idx = 1 if body and isinstance(body[0], ast.Expr) and isinstance(
        getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str) else 0
    return idx < len(body) and isinstance(body[idx], ast.ImportFrom) and body[idx].module == "__future__"


# ---- the design, pinned ----------------------------------------------------------------------
def test_discovered_gates_match_the_design():
    gs = _live_gates()
    assert {g.id for g in gs} == EXPECTED_LIVE_GATE_IDS
    assert len(gs) == len(EXPECTED_LIVE_GATE_IDS)
    assert [g.id for g in gs] == sorted(g.id for g in gs)   # deterministic: sorted by id


def test_each_live_gate_exports_a_well_formed_CHECK():
    for g in _live_gates():
        assert isinstance(g, Check)
        assert callable(g.run)
        assert g.applies_at == "Stop"
        assert g.may_block is True
        # the CHECK (or EXTRA_CHECKS entry) lives in the merged adapter+engine module.
        home = g.run.__module__
        assert home.startswith("makoto.checks.")
        assert home.rsplit(".", 1)[-1] in GATE_MODULE_STEMS
        mod = importlib.import_module(home)
        # the module's own CHECK export IS the gate, EXCEPT contractOrder's dual Pre+Stop surface,
        # whose Stop-side lives in EXTRA_CHECKS instead (its CHECK is the Pre-side, applies_at=Pre).
        assert getattr(mod, "CHECK", None) is g or g in (getattr(mod, "EXTRA_CHECKS", None) or [])


def test_gate_dataclass_has_no_undeclared_shadow_state():
    fields = {f.name for f in dataclasses.fields(Check)}
    assert fields == EXPECTED_GATE_FIELDS
    # may_block IS the structural blocking-eligibility signal (replacing GATE-export presence) --
    # not a shadow tier because it's a total, testable partition: every live gate id is may_block
    # True, and nothing else claims to be. staleEstablisher/undeclaredFalsifiable are Stop-edge
    # CHECKs too but stay may_block=False -- discovered and run, but structurally excluded from
    # _blocking_gate_ids() regardless of their own .level, never a silent in-between state.
    live_ids = {g.id for g in _live_gates()}
    assert live_ids == EXPECTED_LIVE_GATE_IDS
    non_blocking_stop_checks = [c for c in load_checks(edge="Stop") if not c.may_block]
    assert non_blocking_stop_checks, "expected at least staleEstablisher/undeclaredFalsifiable"
    assert {c.id for c in non_blocking_stop_checks}.isdisjoint(EXPECTED_LIVE_GATE_IDS)


def test_gate_context_carries_the_substrate_and_derives_roots():
    fields = {f.name for f in dataclasses.fields(GateContext)}
    assert fields == EXPECTED_CONTEXT_FIELDS
    assert isinstance(GateContext.roots, property)          # roots is derived (= [cwd]), not stored


def test_gatecontext_has_history_field():
    # the faithful events-table source (D-history-source): fabrication gates walk ctx.history
    # (full commands + full tool_responses) like predicate content.unsourced_webfetch — NOT the lossy ledger.
    names = {f.name for f in dataclasses.fields(GateContext)}
    assert "history" in names


def test_package_file_shape_matches_the_design():
    # checks/ is the SHARED flat home for every check (prechecks, forbiddenLocation, the
    # completeness check, and this gate subset) — a subset check, not exact-set equality.
    present = {p.name for p in GATES_DIR.glob("*.py")}
    assert EXPECTED_GATE_FILES <= present, f"missing gate files: {EXPECTED_GATE_FILES - present}"
    assert not (GATES_DIR / "_dark").exists()                    # dark tier CUT (io-purge B3) — Bible holds the designs
    assert len(GATE_MODULE_FILES & present) == 19                # 7 ledger-gates + liveness + self_wired +
    # hollow_test + canon + the 2 canon-fingerprint gates (SPEC-5 Task 9) + contractOrder (SPEC-5,
    # Makoto absorbs Assay) + relativePathCitation + planItemDrift (2026-07-09) + claimedRunningAbsent
    # (2026-07-23) + runIntentUnfulfilled (2026-07-23)


def test_module_function_counts_match_the_design():
    for name, n in EXPECTED_FUNCTION_COUNTS.items():
        assert _def_count((GATES_DIR / name).read_text()) == n, f"{name}: expected {n} top-level defs"


def test_each_gate_module_follows_the_house_style():
    for stem in GATE_MODULE_STEMS:
        f = GATES_DIR / f"{stem}.py"
        src = f.read_text()
        assert _leads_with_future_import(src), f"{f.name}: missing future header"
        assert "\nCHECK = " in src or "\nEXTRA_CHECKS = " in src, \
            f"{f.name}: Stop-edge CHECK/EXTRA_CHECKS export missing/misplaced"


# ---- teeth: every shape predicate must go RED on a planted violation --------------------------
# (the import-firewall predicates + their TEETH moved to tests/test_import_direction.py, seam 7;
#  both planted edges — a sibling named gate and gate->state.commitments — are still asserted
#  RED there, in test_TEETH_direction_checker_rejects_planted_backward_edges.)


def test_TEETH_no_shadow_field_check_catches_a_planted_blocking_field():
    @dataclasses.dataclass(frozen=True)
    class PlantedGate:
        id: str
        applies_at: str
        posture: str
        run: object
        may_block: bool
        blocking: bool                                     # a re-introduced SECOND shadow field
    fields = {f.name for f in dataclasses.fields(PlantedGate)}
    assert "blocking" in fields and fields != EXPECTED_GATE_FIELDS  # the real assertion would redden


def test_TEETH_may_block_partition_catches_a_leaked_advisory_id():
    planted_non_blocking_ids = {"gate.stale_establisher", "gate.undeclared_falsifiable", "gate.completion"}
    assert not planted_non_blocking_ids.isdisjoint(EXPECTED_LIVE_GATE_IDS)  # the real assertion would redden


def test_TEETH_function_count_check_catches_a_drift():
    planted = "def a():\n    pass\ndef b():\n    pass\n"
    assert _def_count(planted) == 2
    assert _def_count(planted) != EXPECTED_FUNCTION_COUNTS["silentlyDroppedCommitment.py"]  # a 6->2 drift reddens


def test_TEETH_discovery_count_is_load_bearing():
    # planting a 5th discovered id (or dropping one) would move this equality — the design count bites.
    assert len(_live_gates()) == len(EXPECTED_LIVE_GATE_IDS)
    assert {"gate.completion", "gate.advance"} < EXPECTED_LIVE_GATE_IDS    # proper subset: set is real
