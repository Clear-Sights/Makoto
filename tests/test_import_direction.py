"""Stage 2 seam 7: the pipeline-ordered file layout IS the layer firewall — every `makoto.*`
import must point at a strictly earlier file in the layout order below. This is the ONE
import-direction meta-test; it replaces the per-file AST firewalls (tests/lib/test_factories.py /
test_io.py / test_claims.py "L1 imports only L0", tests/test_retraction_home.py
"commitments_only_imports_downward", and tests/test_gate_shape.py's ALLOWED_IMPORT_ROOTS +
sibling-gate allowlist).

The plan's proposed order (vocab -> state -> registry -> kit -> checks -> verdict -> ...) was
aspirational in two places; the REAL, verified module graph is ranked below:
  - `verdict.py` is a near-leaf (posture vocabulary): staleEstablisher/undeclaredFalsifiable
    import its ADVISE constant, so verdict ranks BELOW checks/, not above.
  - `state/` imports `kit` and the checks-package L0 re-exports (`makoto.checks` bare), so it
    ranks ABOVE them, not before registry/kit.
Two deliberate call-time back-edges (lazy imports that break cycles) are named exceptions.
"""
import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "plugin" / "makoto"

_RANK = {  # the layout order: an import may only point at a strictly lower rank
    "makoto": 0, "makoto.vocab": 0, "makoto.core": 0, "makoto.registry": 0,   # leaves
    "makoto.kit": 1,
    "makoto.substrate": 2,        # siblings may import each other (cohesive helper pool)
    "makoto.verdict": 3, "makoto.checks#pkg": 3,   # checks/__init__ + _worldpaths: L0 re-exports
    "makoto.state": 4,            # siblings may import each other (one sqlite store)
    "makoto.checks": 5,           # the NAMED check modules — siblings stay firewalled (L2->L2)
    "makoto.context": 6,
    "makoto.dispatch": 7,
    "makoto.configchange": 8,
    "makoto.install": 9, "makoto.events": 9,
    "makoto.__main__": 10,        # the CLI entrypoint drives install + everything below
}
_SIBLING_OK = {"makoto.substrate", "makoto.state"}
_CALL_TIME_OK = {  # documented lazy imports, each breaking a cycle at call time
    ("makoto.kit", "makoto.checks.namedTestTeeth"),   # kit.compute_delta's parser reuse
    ("makoto.verdict", "makoto.dispatch"),            # recheck certificate's lazy fold hooks
}
# named checks may reach into state/ ONLY for these two read surfaces (the old curated
# allowlist's survivors) — never plan/commitments/store (contractOrder duplicates its 12 lines
# of plans SQL on purpose; see test_no_alpha_duplicate_functions._EXEMPT_PAIRS).
_CHECKS_STATE_OK = {"makoto.state.ledger", "makoto.state.citations"}


def _group(mod: str) -> str:
    if mod in ("makoto.checks", "makoto.checks._worldpaths"):
        return "makoto.checks#pkg"
    for g in ("makoto.checks", "makoto.state", "makoto.substrate", "makoto.core"):
        if mod == g or mod.startswith(g + "."):
            return g
    return mod


def _edge_ok(importer: str, target: str) -> bool:
    if (importer, target) in _CALL_TIME_OK:
        return True
    gi, gt = _group(importer), _group(target)
    if gi == "makoto.checks" and gt == "makoto.state":
        return target in _CHECKS_STATE_OK
    ri, rt = _RANK[gi], _RANK[gt]                 # KeyError = new module, place it in the order
    return rt < ri or (rt == ri and gi == gt and gi in _SIBLING_OK)


def _module_of(path: Path) -> str:
    parts = ("makoto",) + path.relative_to(PKG).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def test_every_import_points_earlier_in_the_layout_order():
    bad = []
    for p in sorted(PKG.rglob("*.py")):
        m = _module_of(p)
        for n in ast.walk(ast.parse(p.read_text())):
            targets = ([n.module] if isinstance(n, ast.ImportFrom) and n.module
                       else [a.name for a in n.names] if isinstance(n, ast.Import) else [])
            for t in targets:
                if t.startswith("makoto") and not _edge_ok(m, t):
                    bad.append(f"{m} -> {t}")
    assert not bad, "backward/lateral import(s) against the pipeline order:\n" + "\n".join(bad)


def test_TEETH_direction_checker_rejects_planted_backward_edges():
    assert not _edge_ok("makoto.kit", "makoto.dispatch")                      # low -> high
    assert not _edge_ok("makoto.checks.namedTestTeeth",
                        "makoto.checks.undischargedCommitment")               # sibling gate
    assert not _edge_ok("makoto.checks.contractOrder", "makoto.state.plan")   # curated state slice
    assert not _edge_ok("makoto.checks.selfMuteGuard", "makoto.context")      # gate -> orchestrator
    assert _edge_ok("makoto.state.ledger", "makoto.state.store")              # sibling store: fine
    assert _edge_ok("makoto.checks.falseGreenClaim", "makoto.kit")            # downward: fine
