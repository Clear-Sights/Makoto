"""tests for PreCheck + Finding dataclasses + load_prechecks.

1.0.3 collapse: dropped forensic-catalog field tests (intent / motivation /
evidence) — those fields moved out of the runtime dataclass into TOML row
comments. load_prechecks silently ignores them when present.
"""
from dataclasses import fields
from makoto.schema import PreCheck, Finding, load_prechecks


def test_pattern_dataclass_fields():
    """PreCheck has the 6 runtime fields with proper defaults."""
    p = PreCheck(id="x", fire_level="error", description="d")
    assert p.id == "x"
    assert p.fire_level == "error"
    assert p.description == "d"
    assert p.retry_hint == ""
    assert p.predicate_module == ""
    assert p.keywords == []


def test_finding_dataclass_fields():
    """Finding has the spec's fields; source_event_id defaults to 0 (unstamped)."""
    f = Finding(pattern_id="1.1", file="lab/foo.py", line=42,
                level="error", message="matched 'startswith(' at line 42")
    assert f.pattern_id == "1.1"
    assert f.line == 42
    assert f.retry_hint == ""
    assert f.snippet == ""
    assert f.source_event_id == 0   # default: built outside the hot path


def test_finding_carries_source_event_id():
    """source_event_id is a settable provenance field — the events.id a finding came from."""
    f = Finding(pattern_id="1.1", file="lab/foo.py", line=42,
                level="error", message="x", source_event_id=99)
    assert f.source_event_id == 99


def test_pattern_dataclass_has_exactly_6_runtime_fields():
    """PreCheck carries id/fire_level/description/retry_hint/predicate_module/keywords."""
    field_names = {f.name for f in fields(PreCheck)}
    assert field_names == {"id", "fire_level", "description",
                           "retry_hint", "predicate_module", "keywords"}


def test_load_prechecks_parses_toml(tmp_path):
    """load_prechecks reads a TOML file into a list[PreCheck]."""
    toml_path = tmp_path / "patterns.toml"
    toml_path.write_text("""
[[pattern]]
id = "1.1"
fire_level = "error"
description = "loosened verifier"
keywords = ["startswith("]
""", encoding="utf-8")
    patterns = load_prechecks(toml_path)
    assert len(patterns) == 1
    assert patterns[0].id == "1.1"
    assert patterns[0].fire_level == "error"


def test_load_prechecks_empty_file(tmp_path):
    """empty TOML returns empty list, no crash."""
    toml_path = tmp_path / "patterns.toml"
    toml_path.write_text("", encoding="utf-8")
    assert load_prechecks(toml_path) == []


def test_load_prechecks_ignores_unknown_toml_keys(tmp_path):
    """TOML rows with extra keys (legacy intent/motivation/evidence) load cleanly."""
    toml_path = tmp_path / "patterns.toml"
    toml_path.write_text("""
[[pattern]]
id = "1.x"
fire_level = "error"
description = "with extras"
keywords = ["foo"]
intent = "catch X"
motivation = "ADR-058"
evidence = ["TP_1_x.md"]
some_future_field = "ignored"
""", encoding="utf-8")
    patterns = load_prechecks(toml_path)
    assert len(patterns) == 1
    assert patterns[0].id == "1.x"
    # Unknown keys silently dropped — no AttributeError
    assert not hasattr(patterns[0], "intent")


def test_load_prechecks_default_path_resolves_to_package_data():
    """load_prechecks() with no arg resolves to the live checks/ catalog (SPEC-C item 2 Pre-tier
    cutover -- the default path is loader-backed, not a direct patterns.toml parse anymore)."""
    patterns = load_prechecks()
    assert len(patterns) >= 8
    ids = {p.id for p in patterns}
    assert "content.verifier_predicate_weakened" in ids and "content.self_mute_guard" in ids


def test_all_active_patterns_have_keywords_and_predicate_module():
    """every pattern has keywords + predicate_module (no disabled tier remains to skip)."""
    patterns = load_prechecks()
    for p in patterns:
        assert p.predicate_module, f"pattern {p.id} missing predicate_module"
        # SPEC-5: prechecks migrated into flat makoto.checks with descriptive names (no longer
        # derivable from the pattern id) -- assert the real invariant that survives the move: a
        # live predicate_module actually rooted under the checks catalog.
        assert p.predicate_module.startswith("makoto.checks."), \
            f"pattern {p.id} has non-catalog predicate_module: {p.predicate_module}"
        assert p.keywords, f"pattern {p.id} missing keywords"


def test_every_pattern_blocks_no_warning_tier():
    """Warning-tier-elimination invariant: EVERY live catalog pattern is fire_level='error'.
    makoto has no non-blocking resting state — a pattern blocks or it is cut."""
    patterns = load_prechecks()
    assert patterns, "catalog must be non-empty"
    assert all(p.fire_level == "error" for p in patterns), \
        {p.id: p.fire_level for p in patterns if p.fire_level != "error"}


def test_load_prechecks_rejects_non_error_fire_level(tmp_path):
    """load_prechecks REJECTS any warning/disabled/shadow row — the tier cannot silently return."""
    import pytest
    for bad in ("warning", "disabled", "shadow", "info"):
        toml = tmp_path / f"p_{bad}.toml"
        toml.write_text(
            f'[[pattern]]\nid = "9.9"\nfire_level = "{bad}"\ndescription = "x"\n',
            encoding="utf-8")
        with pytest.raises(ValueError, match="no non-blocking tier"):
            load_prechecks(toml)
