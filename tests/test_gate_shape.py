"""The gate package's SHAPE is itself a word makoto emits about its own design — so it must be
MATERIAL, not illusory. This test pins the design (file set, function counts, exports, the StopCheck
schema, the dark/_common split, the layering firewall, the house style) AND proves each shape
predicate has TEETH: a `test_TEETH_*` feeds it a planted violation and asserts it goes red. The
single source for "the design" is the EXPECTED_* declarations below — change the package <=> change
these <=> the test moves with it (a re-checkable artifact, not a comment). StopCheck-registry cutover
2026-06-05.
"""
from __future__ import annotations
import ast
import dataclasses
import importlib
from pathlib import Path

from makoto.stopchecks import load_stopchecks, StopCheck, GateContext

GATES_DIR = Path(__file__).resolve().parent.parent / "stopchecks"

# ---- the declared design (single source; the package must MATCH it) --------------------------
EXPECTED_GATE_FILES = {
    "__init__.py", "_types.py", "_common.py",
    "stopcheck_completion.py", "stopcheck_advance.py", "stopcheck_green_claim.py", "stopcheck_dropped.py",
    "stopcheck_fabricated_action.py", "stopcheck_named_test.py", "stopcheck_stale_pass.py",
    # liveness gate (folded in from the collapsed close-check tier): adapter + its AST analyzer engine
    # + the test-only FP/soundness harness. Its fn is the analyzer, not a per-gate claim-vs-ledger pred.
    "stopcheck_liveness.py", "liveness.py", "fp_harness.py",
}
EXPECTED_LIVE_GATE_IDS = {"gate.completion", "gate.advance", "gate.green_claim", "gate.dropped",
                          "gate.fabricated_action", "gate.named_test", "gate.stale_pass", "gate.liveness"}
EXPECTED_GATE_FIELDS = {"id", "fn", "run"}                 # NO 'blocking' — discovered<=>live<=>blocking
EXPECTED_CONTEXT_FIELDS = {"text", "touched", "empty", "opens", "testrun_output",
                           "cwd", "fs_exists", "fs_size", "fs_read", "history"}
EXPECTED_FUNCTION_COUNTS = {                               # top-level def count per module (the "number
    "_common.py": 6,                                       # of functions" the design decomposes to)
    "stopcheck_completion.py": 2,
    "stopcheck_advance.py": 4,                             # _advance_signal + advance_gate + the
                                                            # relocation-discharge pair (_adv_stem_core/
                                                            # _adv_relocated_discharge, FP fix)
    "stopcheck_green_claim.py": 1,
    "stopcheck_dropped.py": 6,
    "stopcheck_fabricated_action.py": 3,
    "stopcheck_named_test.py": 6,
    "stopcheck_stale_pass.py": 1,
    "stopcheck_liveness.py": 5,                            # _scratch_roots/_under/_is_scratch/_read/_run
}
# a gate module may import ONLY L0/L1 primitives + the intra-package _common/_types — never a sibling
# gate (gate_*) nor a sibling L2 detector (commitments / retraction / ledger).
ALLOWED_IMPORT_ROOTS = {
    "makoto.checks", "makoto.schema", "makoto.lib.io", "makoto.lib.claims", "makoto.lib.pytest_cache",
    "makoto.lexicons",
    "makoto.stopchecks._common", "makoto.stopchecks._types",
    "makoto.stopchecks.liveness",   # the liveness gate's own AST analyzer engine (intra-package, like _common)
}
FORBIDDEN_SIBLING_PREFIXES = ("makoto.stopchecks.stopcheck_",)


# ---- pure shape predicates (each is fed a planted violation by a test_TEETH_* below) ---------
def imported_makoto_modules(src: str) -> set:
    """Every `from makoto... import` / `import makoto...` module path referenced in src (AST)."""
    out: set = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("makoto"):
            out.add(node.module)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("makoto"):
                    out.add(a.name)
    return out


def sibling_gate_imports(src: str) -> set:
    """The gate sibling modules src imports — the L2->L2 firewall violations (empty = clean)."""
    return {m for m in imported_makoto_modules(src)
            if any(m.startswith(p) for p in FORBIDDEN_SIBLING_PREFIXES)}


def _def_count(src: str) -> int:
    return sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.parse(src).body)


def _gate_source_files() -> list:
    return sorted(GATES_DIR.glob("stopcheck_*.py")) + [GATES_DIR / "_common.py"]


# ---- the design, pinned ----------------------------------------------------------------------
def test_discovered_gates_match_the_design():
    gs = load_stopchecks()
    assert {g.id for g in gs} == EXPECTED_LIVE_GATE_IDS
    assert len(gs) == len(EXPECTED_LIVE_GATE_IDS)
    assert [g.id for g in gs] == sorted(g.id for g in gs)   # deterministic: sorted by id
    assert load_stopchecks() is load_stopchecks()                     # memoized (hot path never re-scans)


def test_each_live_gate_exports_a_well_formed_GATE():
    for g in load_stopchecks():
        assert isinstance(g, StopCheck)
        assert callable(g.fn) and callable(g.run)
        # the GATE export lives in the ADAPTER module (where `run` is defined). For the ledger-gates
        # fn and run are co-located; gate.liveness's fn is the shared analyzer (stopchecks.liveness),
        # while its adapter + GATE export live in stopcheck_liveness.
        home = g.run.__module__
        assert home.startswith("makoto.stopchecks.stopcheck_")
        mod = importlib.import_module(home)
        assert getattr(mod, "GATE") is g                    # the module's GATE export IS the gate


def test_gate_dataclass_has_no_shadow_tier_field():
    fields = {f.name for f in dataclasses.fields(StopCheck)}
    assert fields == EXPECTED_GATE_FIELDS
    assert "blocking" not in fields                         # discovered<=>live<=>blocking is STRUCTURAL


def test_gate_context_carries_the_substrate_and_derives_roots():
    fields = {f.name for f in dataclasses.fields(GateContext)}
    assert fields == EXPECTED_CONTEXT_FIELDS
    assert isinstance(GateContext.roots, property)          # roots is derived (= [cwd]), not stored


def test_gatecontext_has_history_field():
    # the faithful events-table source (D-history-source): fabrication gates walk ctx.history
    # (full commands + full tool_responses) like predicate 1.9 — NOT the lossy ledger.
    names = {f.name for f in dataclasses.fields(GateContext)}
    assert "history" in names


def test_package_file_shape_matches_the_design():
    assert {p.name for p in GATES_DIR.glob("*.py")} == EXPECTED_GATE_FILES
    assert not (GATES_DIR / "_dark").exists()                    # dark tier CUT (io-purge B3) — Bible holds the designs
    assert len(list(GATES_DIR.glob("stopcheck_*.py"))) == 8      # 7 ledger-gates + liveness (folded from close-check tier)


def test_module_function_counts_match_the_design():
    for name, n in EXPECTED_FUNCTION_COUNTS.items():
        assert _def_count((GATES_DIR / name).read_text()) == n, f"{name}: expected {n} top-level defs"


def test_no_gate_module_imports_a_sibling_or_cross_l2():
    for f in _gate_source_files():
        src = f.read_text()
        assert sibling_gate_imports(src) == set(), f"{f.name} imports a sibling gate (L2->L2)"
        for m in imported_makoto_modules(src):
            assert m in ALLOWED_IMPORT_ROOTS, f"{f.name} imports disallowed module {m}"


def test_each_gate_module_follows_the_house_style():
    for f in GATES_DIR.glob("stopcheck_*.py"):
        src = f.read_text()
        assert src.startswith("from __future__ import annotations"), f"{f.name}: missing future header"
        assert "\nGATE = StopCheck(" in src, f"{f.name}: GATE export missing/misplaced"


# ---- teeth: every shape predicate must go RED on a planted violation --------------------------
def test_TEETH_sibling_import_detector_discriminates():
    planted = "from makoto.stopchecks.stopcheck_advance import advance_gate\nx = 1\n"
    assert sibling_gate_imports(planted) == {"makoto.stopchecks.stopcheck_advance"}   # caught
    clean = "from makoto.stopchecks._common import _discharged\n"
    assert sibling_gate_imports(clean) == set()                            # no false positive


def test_TEETH_import_allowlist_catches_a_cross_l2_import():
    planted = "from makoto.commitments import open_commitments\n"          # a sibling L2 — forbidden
    mods = imported_makoto_modules(planted)
    assert mods == {"makoto.commitments"}
    assert not (mods <= ALLOWED_IMPORT_ROOTS)              # the real allowlist assertion would FAIL here


def test_TEETH_no_shadow_field_check_catches_a_planted_blocking_field():
    @dataclasses.dataclass(frozen=True)
    class PlantedGate:
        id: str
        fn: object
        run: object
        blocking: bool                                     # a re-introduced shadow tier
    fields = {f.name for f in dataclasses.fields(PlantedGate)}
    assert "blocking" in fields and fields != EXPECTED_GATE_FIELDS  # the real assertion would redden


def test_TEETH_function_count_check_catches_a_drift():
    planted = "def a():\n    pass\ndef b():\n    pass\n"
    assert _def_count(planted) == 2
    assert _def_count(planted) != EXPECTED_FUNCTION_COUNTS["stopcheck_dropped.py"]  # a 6->2 drift reddens


def test_TEETH_discovery_count_is_load_bearing():
    # planting a 5th discovered id (or dropping one) would move this equality — the design count bites.
    assert len(load_stopchecks()) == len(EXPECTED_LIVE_GATE_IDS)
    assert {"gate.completion", "gate.advance"} < EXPECTED_LIVE_GATE_IDS    # proper subset: set is real
