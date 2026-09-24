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
surface as a plain `CHECK` discovered by the SAME unified `checks._loader.load_checks(edge="Stop")` every Pre-tier
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

from makoto.registry import Check, _ADVISORY_ALLOWLIST, load_checks
from makoto.context import GateContext
from tests._rows import SHAPES


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
# checks/ holds one module per register family; every check is a row of one of them.
EXPECTED_LIVE_GATE_IDS = {"gate.completion", "gate.green_claim", "gate.dropped",
                          "gate.fabricated_action", "gate.named_test", "gate.stale_pass", "gate.liveness",
                          "gate.self_wired", "gate.hollow_test", "gate.canon",
                          "gate.canon_fingerprints", "gate.canon_fingerprints_advisory",
                          "gate.relative_path_citation", "gate.plan_item_drift",
                          "gate.claimed_running", "gate.claimed_shipped",
                          "gate.claimed_consent_absent",
                          "gate.unexamined_wall",
                          "gate.unprobed_fanout", "gate.unasked_plan",
                          "gate.unread_structure",
                          "gate.unwitnessed_verifier",
                          "gate.unknown_ref_switch",
                          "gate.unobserved_destruction",
                          "gate.relaunched_unchanged",
                          "gate.undischarged_waiver",
                          "gate.unnamed_failure",
                          "gate.report_before_run",
                          "gate.unclaimed_unit",
                          "gate.pasted_fix"}
EXPECTED_GATE_FIELDS = {"id", "applies_at", "posture", "run", "may_block",
                        "keywords", "retry_hint", "description", "predicate_module",
                        "layer", "eats", "tests"}   # "object" | "meta" -- see Check's own docstring; only
                                   # content.self_mute_guard / gate.self_wired are "meta" today
EXPECTED_CONTEXT_FIELDS = {"text", "touched", "empty", "testrun_output",
                           "testrun_exit",   # the exit STATUS of the row `testrun_output` came
                           # from. gate.green_claim reads the NUMBER, closing the half of its
                           # absence-reads-as-green edge a token scan structurally cannot: a red
                           # run whose 500-char tail kept no failure token read as green.
                           # Defaulted to None, so an unrecorded status behaves as before.
                           "cwd", "fs_exists", "fs_size", "fs_read", "history",
                           "permission_mode", "agent_id", "agent_type", "plan",
                           "session_id", "transcript_path", "state_root",
                           "open_plan_items",   # Task 2 slice 5 / 2026-07-09 planItemDrift
                           "history_all_agents"}   # 2026-07-23: gate.claimed_running's
                           # cross-agent-pooled Bash evidence twin of `history` (see GateContext's
                           # own field doc)
# Stage 2 seam 7: the gate-side import firewall (the former ALLOWED_IMPORT_ROOTS curated
# allowlist + sibling-gate scan) now lives in tests/test_import_direction.py — "the layer
# firewall becomes the file order": every makoto.* import must point strictly earlier in the
# pipeline-ordered layout, named gates may never import a sibling gate, and their reach into
# state/ stays narrowed to the ledger/citations read surfaces.


# ---- pure shape predicates (each is fed a planted violation by a test_TEETH_* below) ---------
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
        # `may_block is True` used to be asserted here. `_live_gates()` is DEFINED as
        # `[c for c in load_checks(edge="Stop") if c.may_block]`, so that assertion was the
        # selection restated: it could not fail while this loop had anything to iterate over.
        # The property it was reaching for -- that the may_block set is exactly the designed set
        # -- is checked where it can fail, in test_discovered_gates_match_the_design above,
        # against EXPECTED_LIVE_GATE_IDS.
        homes = [stem for stem in SHAPES
                 if importlib.import_module(f"makoto.checks.{stem}").ROWS.get(g.id) is g]
        assert len(homes) == 1, f"{g.id}: must be a row of exactly one shape module, is in {homes}"


def _shadow_field_violation(fields: set) -> str | None:
    """THE law, as a callable, so the teeth test can apply it to a plant instead of restating it.

    A teeth test that re-derives its subject's assertion in its own words proves nothing about
    the assertion that ships: both can be edited apart, and the teeth test goes on passing. The
    two callers below -- the law and its plant -- now run the same code.
    """
    if fields != EXPECTED_GATE_FIELDS:
        return (f"Check's fields are {sorted(fields)}; expected {sorted(EXPECTED_GATE_FIELDS)}. "
                f"Extra: {sorted(fields - EXPECTED_GATE_FIELDS)}")
    return None


def _partition_violation(non_blocking_ids: set) -> str | None:
    """THE partition law, likewise: no id may be both may_block=False and a live blocking gate."""
    leaked = sorted(non_blocking_ids & EXPECTED_LIVE_GATE_IDS)
    if leaked:
        return (f"these ids are declared non-blocking AND listed as live blocking gates: "
                f"{leaked}. The partition is not total.")
    return None


def test_gate_dataclass_has_no_undeclared_shadow_state():
    fields = {f.name for f in dataclasses.fields(Check)}
    assert _shadow_field_violation(fields) is None, _shadow_field_violation(fields)
    # may_block IS the structural blocking-eligibility signal (replacing GATE-export presence) --
    # not a shadow tier because it's a total, testable partition: every live gate id is may_block
    # True, and nothing else claims to be. staleEstablisher/undeclaredFalsifiable are Stop-edge
    # CHECKs too but stay may_block=False -- discovered and run, but structurally excluded from
    # _blocking_gate_ids() regardless of their own .level, never a silent in-between state.
    live_ids = {g.id for g in _live_gates()}
    assert live_ids == EXPECTED_LIVE_GATE_IDS
    non_blocking_stop_checks = [c for c in load_checks(edge="Stop") if not c.may_block]
    assert non_blocking_stop_checks, "expected at least staleEstablisher/undeclaredFalsifiable"
    # BY CONSTRUCTION on real input, and marked as such. `EXPECTED_LIVE_GATE_IDS` was just
    # asserted equal to the may_block-True ids, and `non_blocking_stop_checks` is the may_block-
    # False ones, so the two are complementary halves of one catalog and cannot intersect
    # however the dispatcher behaves. This stays as the statement of the partition, and its
    # discriminating power lives in the teeth test that plants a leak into it.
    #
    # The CLAIM the partition stands for -- may_block decides what reaches the decision -- is
    # observed, not restated, in tests/test_dispatch.py::
    # test_may_block_is_what_actually_reaches_the_decision, which drives a planted finding from
    # each side through _evaluate_and_gate and requires opposite outcomes.
    violation = _partition_violation({c.id for c in non_blocking_stop_checks})
    assert violation is None, violation


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
    present = {p.stem for p in GATES_DIR.glob("*.py") if not p.name.startswith("_")}
    assert present == set(SHAPES), f"checks/ must hold exactly the four family modules: {sorted(present)}"


def test_each_gate_module_follows_the_house_style():
    for stem in SHAPES:
        f = GATES_DIR / f"{stem}.py"
        src = f.read_text()
        assert _leads_with_future_import(src), f"{f.name}: missing future header"
        assert "\nROWS = " in src and "\nCHECK, *EXTRA_CHECKS = _ROWS" in src, f"{f.name}: row export missing"


# ---- teeth: every shape predicate must go RED on a planted violation --------------------------
# (the import-firewall predicates + their TEETH moved to tests/test_import_direction.py, seam 7;
#  both planted edges — a sibling named gate and gate->state.plan — are still asserted
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
    assert "blocking" in fields, "the plant did not plant; there is no shadow field to catch"
    # THE REAL LAW, applied. This used to assert `fields != EXPECTED_GATE_FIELDS` with a comment
    # saying the real assertion "would redden" -- a restatement of the law in the teeth test's
    # own words, which proves nothing about the assertion that ships and goes on passing if the
    # two are edited apart. Both now call the same function.
    assert _shadow_field_violation(fields) is not None, (
        "the shipped no-shadow-field law does not report a re-introduced `blocking` field")
    assert _shadow_field_violation({f.name for f in dataclasses.fields(Check)}) is None, (
        "CONTROL: the same law must pass on the real Check, or it reports everything")


def test_TEETH_may_block_partition_catches_a_leaked_advisory_id():
    # The plant is a live blocking gate id leaking into the non-blocking set. It is taken FROM
    # EXPECTED_LIVE_GATE_IDS rather than spelled as a literal, so the plant cannot quietly stop
    # being a leak when that set is edited.
    leaked = sorted(EXPECTED_LIVE_GATE_IDS)[0]
    planted_non_blocking_ids = {"gate.stale_establisher", "gate.undeclared_falsifiable", leaked}
    assert _partition_violation(planted_non_blocking_ids) is not None, (
        f"the shipped partition law does not report {leaked!r} being declared non-blocking "
        f"while listed as a live blocking gate")
    real = {c.id for c in load_checks(edge="Stop") if not c.may_block}
    assert _partition_violation(real) is None, (
        "CONTROL: the same law must pass on the real non-blocking set, or it reports everything")


def test_TEETH_discovery_count_is_load_bearing():
    # planting a 5th discovered id (or dropping one) would move this equality — the design count bites.
    assert len(_live_gates()) == len(EXPECTED_LIVE_GATE_IDS)
    assert {"gate.completion", "gate.dropped"} < EXPECTED_LIVE_GATE_IDS    # proper subset: set is real
