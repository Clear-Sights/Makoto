"""makoto.substrate._loader.load_checks — the flat checks/ package's own discovery mechanism
(SPEC-5 Task 2). Supersedes nothing yet: `schema.load_prechecks`/`substrate._loader.load_stopchecks`
keep working unchanged this task (Task 3/4 migrate their real callers later).

Every scenario here scans an ISOLATED tmp_path directory via `load_checks(package_dir=...)`
rather than the real `makoto/checks/` package, so this file stays correct forever regardless of
how many real detector modules Tasks 3-9 land into the real folder (today: zero besides
`undeclaredFalsifiable.py`, landed by this same task's Part B; eventually ~60). The one
exception is the dead-package regression guard, which is about import identity, not catalog
contents.
"""
import importlib

import pytest

from makoto.substrate._loader import Check, load_checks


def _write(tmp_path, name, id_, applies_at, posture="advise"):
    (tmp_path / name).write_text(
        "from makoto.substrate._loader import Check\n"
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


def test_existing_prechecks_and_stopchecks_loaders_unaffected():
    # Non-breaking guarantee: the new checks/ taxonomy is additive. The two existing loaders
    # this task explicitly does not touch/supersede keep discovering their real catalogs.
    from makoto.core.schema import load_prechecks
    from makoto.substrate._loader import load_checks

    assert load_prechecks(), "prechecks still discovered unchanged"
    assert load_checks(edge="Stop"), "stop checks still discovered unchanged"
