"""tests for PreCheck + Finding dataclasses, and the relocated TOML-pattern-fixture parser.

1.0.3 collapse: dropped forensic-catalog field tests (intent / motivation /
evidence) — those fields moved out of the runtime dataclass into TOML row
comments. load_toml_patterns silently ignores them when present.

2026-08-16: `schema.load_prechecks()` (the TOML/loader-adapter shim) was retired once
`dispatch.py`'s hot path (and every other caller) migrated to
`registry.load_precheck_catalog()`. The default-path (live catalog) tests that used to
live here now live in `tests/test_pre_tier_block_invariant.py` and the various
`registry`-facing tests; the explicit-`path` TOML-parsing tests below now exercise the
relocated `tests/_toml_pattern_fixture.load_toml_patterns`, which was never anything but a
test-fixture helper in the first place.
"""
from dataclasses import fields
import pytest
from makoto.vocab import PreCheck, Finding
from tests._toml_pattern_fixture import load_toml_patterns


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
    f = Finding(pattern_id="content.verifier_predicate_weakened", file="lab/foo.py", line=42,
                level="error", message="matched 'startswith(' at line 42")
    assert f.pattern_id == "content.verifier_predicate_weakened"
    assert f.line == 42
    assert f.retry_hint == ""
    assert f.snippet == ""
    assert f.source_event_id == 0   # default: built outside the hot path


def test_finding_carries_source_event_id():
    """source_event_id is a settable provenance field — the events.id a finding came from."""
    f = Finding(pattern_id="content.verifier_predicate_weakened", file="lab/foo.py", line=42,
                level="error", message="x", source_event_id=99)
    assert f.source_event_id == 99


def test_pattern_dataclass_has_exactly_6_runtime_fields():
    """PreCheck carries id/fire_level/description/retry_hint/predicate_module/keywords."""
    field_names = {f.name for f in fields(PreCheck)}
    assert field_names == {"id", "fire_level", "description",
                           "retry_hint", "predicate_module", "keywords"}


def test_load_toml_patterns_parses_toml(tmp_path):
    """load_toml_patterns reads a TOML file into a list[PreCheck]."""
    toml_path = tmp_path / "patterns.toml"
    toml_path.write_text("""
[[pattern]]
id = "content.verifier_predicate_weakened"
fire_level = "error"
description = "loosened verifier"
keywords = ["startswith("]
""", encoding="utf-8")
    patterns = load_toml_patterns(toml_path)
    assert len(patterns) == 1
    assert patterns[0].id == "content.verifier_predicate_weakened"
    assert patterns[0].fire_level == "error"


def test_load_toml_patterns_empty_file(tmp_path):
    """empty TOML returns empty list, no crash."""
    toml_path = tmp_path / "patterns.toml"
    toml_path.write_text("", encoding="utf-8")
    assert load_toml_patterns(toml_path) == []


def test_load_toml_patterns_ignores_unknown_toml_keys(tmp_path):
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
    patterns = load_toml_patterns(toml_path)
    assert len(patterns) == 1
    assert patterns[0].id == "1.x"
    # Unknown keys silently dropped — no AttributeError
    assert not hasattr(patterns[0], "intent")


def test_load_toml_patterns_rejects_non_error_fire_level(tmp_path):
    """load_toml_patterns REJECTS any warning/disabled/shadow row — the tier cannot silently return."""
    for bad in ("warning", "disabled", "shadow", "info"):
        toml = tmp_path / f"p_{bad}.toml"
        toml.write_text(
            f'[[pattern]]\nid = "9.9"\nfire_level = "{bad}"\ndescription = "x"\n',
            encoding="utf-8")
        with pytest.raises(ValueError, match="no non-blocking tier"):
            load_toml_patterns(toml)
