"""Tests for the structural ``gate.catalog_completeness`` check.

The check owns loader/manifest structure only. It does not claim that registered predicates are
behaviorally falsifiable.
"""
from makoto.checks.catalogCompleteness import (
    CHECK,
    catalog_completeness_gate,
    orphan_ids,
    orphan_modules,
)


def _good(tmp_path, name, id_, applies_at="Stop"):
    (tmp_path / name).write_text(
        "from makoto.substrate._loader import Check\n"
        f"CHECK = Check(id={id_!r}, applies_at={applies_at!r}, posture='advise')\n"
    )


def test_no_orphans_on_a_fully_consistent_catalog(tmp_path):
    _good(tmp_path, "sample.py", "x.sample")
    assert orphan_modules(package_dir=tmp_path) == []
    assert orphan_ids(package_dir=tmp_path, declared={"x.sample": "sample"}) == []
    assert catalog_completeness_gate(
        package_dir=tmp_path, declared={"x.sample": "sample"}
    ) is None


def test_module_with_no_check_object_is_an_orphan_module(tmp_path):
    _good(tmp_path, "good.py", "x.good")
    (tmp_path / "unregistered.py").write_text("VALUE = 1\n")
    assert orphan_modules(package_dir=tmp_path) == ["unregistered"]


def test_module_with_a_malformed_check_is_an_orphan_module(tmp_path):
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


def test_declared_id_with_no_backing_module_is_an_orphan_id(tmp_path):
    _good(tmp_path, "live.py", "x.live")
    declared = {"x.live": "live", "x.ghost": "ghost_module_never_written"}
    assert orphan_ids(package_dir=tmp_path, declared=declared) == ["x.ghost"]


def test_extra_checks_are_live_members_for_manifest_completeness(tmp_path):
    (tmp_path / "family.py").write_text(
        "from makoto.substrate._loader import Check\n"
        "CHECK = Check(id='x.first', applies_at='Pre', posture='BLOCK')\n"
        "EXTRA_CHECKS = [Check(id='x.second', applies_at='Pre', posture='BLOCK')]\n"
    )
    declared = {"x.first": "family", "x.second": "family"}
    assert orphan_ids(package_dir=tmp_path, declared=declared) == []


def test_empty_manifest_yields_no_orphan_ids(tmp_path):
    _good(tmp_path, "live.py", "x.live")
    assert orphan_ids(package_dir=tmp_path, declared={}) == []


def test_gate_reports_both_orphan_kinds_together(tmp_path):
    _good(tmp_path, "live.py", "x.live")
    (tmp_path / "unregistered.py").write_text("VALUE = 1\n")
    declared = {"x.live": "live", "x.ghost": "ghost_module"}
    finding = catalog_completeness_gate(package_dir=tmp_path, declared=declared)
    assert finding is not None
    assert finding.pattern_id == "gate.catalog_completeness"
    assert finding.level == "advisory"
    assert "unregistered" in finding.message
    assert "x.ghost" in finding.message


def test_gate_is_advisory_and_structurally_never_blocking():
    from makoto.verdict.posture import ADVISE
    assert CHECK.posture == ADVISE
    assert CHECK.may_block is False


def test_real_catalog_has_zero_drift_at_rest():
    assert catalog_completeness_gate() is None


def test_check_is_discovered_by_load_checks():
    from makoto.substrate._loader import load_checks
    ids = {c.id for c in load_checks(edge="Stop")}
    assert "gate.catalog_completeness" in ids


def test_check_export_shape():
    assert CHECK.id == "gate.catalog_completeness"
    assert CHECK.applies_at == "Stop"
    assert callable(CHECK.run)
