"""makoto.registry.load_checks — the flat checks/ package's own discovery mechanism
(SPEC-5 Task 2). Now the SOLE discovery path for both edges (2026-08-16): `schema.load_prechecks`
was retired once its real callers migrated to `load_checks`/`load_precheck_catalog`, and the old
`registry.load_stopchecks` was retired earlier (2026-07-10, see `_loader.py`'s own
docstring).

Every scenario here scans an ISOLATED tmp_path directory via `load_checks(package_dir=...)`
rather than the real `makoto/checks/` package, so this file stays correct forever regardless of
how many real detector modules Tasks 3-9 land into the real folder (today: zero besides
`undeclaredFalsifiable.py`, landed by this same task's Part B; eventually ~60). The one
exception is the dead-package regression guard, which is about import identity, not catalog
contents.
"""
import importlib

import pytest

from makoto.registry import Check, load_checks


def _write(tmp_path, name, id_, applies_at, posture="ADVISE"):
    (tmp_path / name).write_text(
        "from makoto.registry import Check\n"
        f"CHECK = Check(id={id_!r}, applies_at={applies_at!r}, posture={posture!r})\n"
    )


def test_empty_folder_of_check_modules_loads_to_empty_list(tmp_path):
    # Only package-plumbing (underscore-prefixed) files present -- no detector module at all.
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "_loader.py").write_text("")
    assert load_checks(package_dir=tmp_path) == []


def test_discovers_a_well_formed_check_module(tmp_path):
    _write(tmp_path, "sample.py", "x.sample", "Pre")
    found = load_checks(package_dir=tmp_path)
    assert len(found) == 1
    assert found[0].id == "x.sample"
    assert found[0].applies_at == "Pre"
    assert isinstance(found[0], Check)


def test_edge_filter_returns_only_matching_applies_at(tmp_path):
    _write(tmp_path, "a.py", "x.a", "Pre")
    _write(tmp_path, "b.py", "x.b", "Stop")
    _write(tmp_path, "c.py", "x.c", "Stop")
    assert {c.id for c in load_checks(edge="Pre", package_dir=tmp_path)} == {"x.a"}
    assert {c.id for c in load_checks(edge="Stop", package_dir=tmp_path)} == {"x.b", "x.c"}
    assert load_checks(edge="SessionStart", package_dir=tmp_path) == []


def test_edge_none_returns_every_valid_check_regardless_of_edge(tmp_path):
    _write(tmp_path, "a.py", "x.a", "Pre")
    _write(tmp_path, "b.py", "x.b", "SubagentStop")
    assert {c.id for c in load_checks(package_dir=tmp_path)} == {"x.a", "x.b"}


def test_underscore_prefixed_files_are_never_treated_as_detector_modules(tmp_path):
    _write(tmp_path, "_hidden.py", "x.hidden", "Pre")
    assert load_checks(package_dir=tmp_path) == []


def test_module_with_no_check_object_is_silently_skipped(tmp_path):
    (tmp_path / "nocheck.py").write_text("VALUE = 1\n")
    assert load_checks(package_dir=tmp_path) == []


def test_check_missing_a_required_field_is_silently_skipped(tmp_path):
    (tmp_path / "malformed.py").write_text("class C: pass\nCHECK = C()\n")  # no id/applies_at/posture
    assert load_checks(package_dir=tmp_path) == []


def test_check_with_invalid_applies_at_is_silently_skipped(tmp_path):
    _write(tmp_path, "wrongedge.py", "x.wrong", "PreToolUse")  # not one of the 5 allowed edges
    assert load_checks(package_dir=tmp_path) == []


def test_module_that_raises_on_import_is_silently_skipped_not_fatal(tmp_path):
    (tmp_path / "boom.py").write_text("raise RuntimeError('deliberately broken')\n")
    assert load_checks(package_dir=tmp_path) == []


def test_collapsed_packages_are_still_gone():
    # Carried forward from test_check_taxonomy.py's (singular) dead-package guard, per the
    # merge plan's Step 1: the collapse is MATERIAL, not just a rename, so a reintroduced
    # closechecks/ or postchecks/ tier reddens here too.
    for dead in ("makoto.closechecks", "makoto.postchecks"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(dead)


def test_load_checks_does_not_import_modules_irrelevant_to_the_requested_edge():
    # Loader-level perf guard (measured regression: load_checks(edge=...) used to import EVERY
    # check module in makoto/checks/ regardless of which edge was requested -- ~35 modules,
    # ~600KB of code, on every single call). This scans the REAL package -- unlike the rest of
    # this file -- because the point is specifically that a Pre-only real module never lands in
    # `sys.modules` for a Stop-edge request, and vice versa. `contractOrder.py` (the one
    # dual Pre+Stop surface via EXTRA_CHECKS) legitimately belongs on both sides, so it is
    # excluded from the "must not appear" sets below.
    import sys

    from makoto.registry import ALLOWED_EDGES, scan

    def _reset_check_modules():
        for mod in list(sys.modules):
            if mod.startswith("makoto.checks.") and mod != "makoto.checks.contractOrder":
                del sys.modules[mod]

    # Ground truth for "which edge does each real module's own CHECK belong to" (stem -> CHECK,
    # from an unfiltered scan() so this test never hardcodes the real catalog by hand). This
    # only sees each module's PRIMARY CHECK, not EXTRA_CHECKS -- fine, since contractOrder.py
    # (the sole EXTRA_CHECKS user) is excluded from both sides below anyway.
    stems_by_edge = {edge: set() for edge in ALLOWED_EDGES}
    for stem, chk in scan().items():
        if chk is not None and stem != "contractOrder":
            stems_by_edge[chk.applies_at].add(stem)

    pre_only_stems = stems_by_edge["Pre"] - stems_by_edge["Stop"]
    stop_only_stems = stems_by_edge["Stop"] - stems_by_edge["Pre"]
    assert pre_only_stems and stop_only_stems  # sanity: real catalog has both kinds

    _reset_check_modules()
    assert load_checks(edge="Stop")
    imported_stems = {m.rsplit(".", 1)[-1] for m in sys.modules if m.startswith("makoto.checks.")}
    assert not (pre_only_stems & imported_stems), (
        "load_checks(edge='Stop') imported Pre-only module(s): "
        f"{pre_only_stems & imported_stems}")

    _reset_check_modules()
    assert load_checks(edge="Pre")
    imported_stems = {m.rsplit(".", 1)[-1] for m in sys.modules if m.startswith("makoto.checks.")}
    assert not (stop_only_stems & imported_stems), (
        "load_checks(edge='Pre') imported Stop-only module(s): "
        f"{stop_only_stems & imported_stems}")


def test_existing_prechecks_and_stopchecks_loaders_unaffected():
    # 2026-08-16: `schema.load_prechecks()` (the loader-adapter shim this comment used to say
    # was "explicitly not touched/superseded") has now been retired -- the migration to a single
    # discovery path completed. Both edges are discovered through the same `registry`
    # entry points today; this test now pins that unified reality instead of the old split.
    from makoto.registry import load_checks, load_precheck_catalog

    live = load_precheck_catalog()
    assert live, "prechecks still discovered unchanged"
    assert all(c.predicate_module for c in live), "every Pre-tier catalog row has a predicate_module"
    assert all(c.keywords for c in live), "every Pre-tier catalog row has >=1 keyword"
    assert load_checks(edge="Stop"), "stop checks still discovered unchanged"
