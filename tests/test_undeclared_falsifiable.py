"""makoto.checks.undeclaredFalsifiable -- SPEC-5 Task 2 Step 6, declared-falsifiability
completeness. Distinct from anything Assay does: Assay forces a claim to *be* falsifiable; this
checks that every piece claiming falsifiability in the checks/ catalog is actually *declared* --
a manifest-vs-reality auditor over the catalog itself. Same Stop-time, advisory-tier shape as
`stopchecks/stopcheck_self_wired.py` (see that module's own predicate-injection style), but
audits `checks/`'s own internal consistency rather than whether the faculty is wired into the
host at all.

Two orphan directions, each planted independently via isolated tmp_path directories /
in-memory manifests -- never by mutating the real live `makoto/checks/` package:
  * ORPHAN MODULE: a `.py` file sits in checks/ but produces no `load_checks()`-discoverable
    CHECK (unregistered -- missing/malformed CHECK, or a mismatched id).
  * ORPHAN ID: an ID is declared in the catalog's manifest but no live module backs it.
"""
from makoto.checks.undeclaredFalsifiable import (
    CHECK,
    orphan_ids,
    orphan_modules,
    undeclared_falsifiable_gate,
)


def _good(tmp_path, name, id_, applies_at="Stop"):
    (tmp_path / name).write_text(
        "from makoto.substrate._loader import Check\n"
        f"CHECK = Check(id={id_!r}, applies_at={applies_at!r}, posture='advise')\n"
    )


# ---- orphan MODULE: exists on disk, not discoverable/registered -------------------------------

def test_no_orphans_on_a_fully_consistent_catalog(tmp_path):
    _good(tmp_path, "sample.py", "x.sample")
    assert orphan_modules(package_dir=tmp_path) == []
    assert orphan_ids(package_dir=tmp_path, declared={"x.sample": "sample"}) == []
    assert undeclared_falsifiable_gate(package_dir=tmp_path, declared={"x.sample": "sample"}) is None


def test_module_with_no_check_object_is_an_orphan_module(tmp_path):
    _good(tmp_path, "good.py", "x.good")
    (tmp_path / "unregistered.py").write_text("VALUE = 1\n")   # no CHECK at all
    assert orphan_modules(package_dir=tmp_path) == ["unregistered"]


def test_module_with_a_malformed_check_is_an_orphan_module(tmp_path):
    # A CHECK object present but with a mismatched/invalid shape (no valid id) never resolves
    # via load_checks() -- unregistered in the loader's eyes despite the file existing.
    (tmp_path / "mismatched.py").write_text(
        "from makoto.substrate._loader import Check\n"
        "CHECK = Check(id='', applies_at='Stop', posture='advise')\n"
    )
    assert orphan_modules(package_dir=tmp_path) == ["mismatched"]


def test_module_that_fails_to_import_is_an_orphan_module(tmp_path):
    (tmp_path / "broken.py").write_text("raise RuntimeError('boom')\n")
    assert orphan_modules(package_dir=tmp_path) == ["broken"]


def test_underscore_files_are_never_orphan_modules(tmp_path):
    (tmp_path / "_helper.py").write_text("VALUE = 1\n")
    assert orphan_modules(package_dir=tmp_path) == []


# ---- orphan ID: declared, no module -------------------------------------------------------

def test_declared_id_with_no_backing_module_is_an_orphan_id(tmp_path):
    _good(tmp_path, "live.py", "x.live")
    declared = {"x.live": "live", "x.ghost": "ghost_module_never_written"}
    assert orphan_ids(package_dir=tmp_path, declared=declared) == ["x.ghost"]


def test_empty_manifest_yields_no_orphan_ids(tmp_path):
    _good(tmp_path, "live.py", "x.live")
    assert orphan_ids(package_dir=tmp_path, declared={}) == []


# ---- the combined gate --------------------------------------------------------------------

def test_gate_reports_both_orphan_kinds_together(tmp_path):
    _good(tmp_path, "live.py", "x.live")
    (tmp_path / "unregistered.py").write_text("VALUE = 1\n")     # orphan module
    declared = {"x.live": "live", "x.ghost": "ghost_module"}      # x.ghost: orphan id
    f = undeclared_falsifiable_gate(package_dir=tmp_path, declared=declared)
    assert f is not None
    assert f.pattern_id == "gate.undeclared_falsifiable"
    assert f.level == "advisory"
    assert "unregistered" in f.message
    assert "x.ghost" in f.message


def test_gate_is_advisory_never_blocking():
    # Never "error" -- per this repo's advisory-over-blocking standing policy, same tier as
    # gate.self_wired.
    from makoto.verdict.posture import ADVISE
    assert CHECK.posture == ADVISE


# ---- the real, live catalog: this check auditing itself ------------------------------------

def test_real_catalog_has_zero_drift_at_rest():
    # Once this module lands, the real checks/ package's own catalog must be self-consistent:
    # this file registers itself in the manifest, so running the gate against the REAL package
    # (no injected declared=/package_dir=) finds nothing to report.
    assert undeclared_falsifiable_gate() is None


def test_check_is_discovered_by_load_checks():
    from makoto.substrate._loader import load_checks
    ids = {c.id for c in load_checks(edge="Stop")}
    assert "gate.undeclared_falsifiable" in ids


def test_check_export_shape():
    assert CHECK.id == "gate.undeclared_falsifiable"
    assert CHECK.applies_at == "Stop"
    assert callable(CHECK.run)
