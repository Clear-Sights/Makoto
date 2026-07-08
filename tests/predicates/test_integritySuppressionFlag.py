"""pattern 1.4 scope sentinels (graduation to BLOCKING, 2026-06-02).

1.4 was scoped to its MATERIAL core: an integrity-named suppression key as a
standalone assignment line in a `.toml` config. Every corpus FP was a `.md` doc
quoting an example; the scope drops `.md`, drops non-integrity perf toggles, and
requires a full-line anchor. These adversarial near-misses prove the
discrimination so a BLOCKING 1.4 cannot regress into firing on documentation,
prose, comments, or perf toggles. (A green corpus alone does not prove low FP —
the corpus simply never exhibited the TP; these sentinels do.)
"""
from __future__ import annotations
from makoto.checks.integritySuppressionFlag import predicate
from makoto.schema import PreCheck

_PAT = PreCheck(id="content.integrity_suppression_flag", fire_level="error",
               description="suppression flag without rationale", retry_hint="x")


def _fires(file_path: str, content: str) -> bool:
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": file_path, "content": content}}
    return predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === TRUE POSITIVES: an integrity-named suppression line in a .toml ============

def test_tp_audit_skip():
    assert _fires("pyproject.toml", "audit_skip = true\n")


def test_tp_verification_bypass():
    assert _fires(".makoto.toml", "verification_bypass = true\n")


def test_tp_integrity_check_inapplicable():
    assert _fires("config.toml", "integrity_check_inapplicable = true\n")


def test_tp_quoted_key():
    assert _fires("config.toml", '"signature_verify_skip" = true\n')


def test_tp_amid_other_config():
    body = "[tool]\nname = \"x\"\nintegrity_check_skip = true\nother = 1\n"
    assert _fires("config.toml", body)


def test_tp_attestation_and_checksum():
    assert _fires("config.toml", "attestation_skip = true\n")
    assert _fires("config.toml", "checksum_verify_bypass = true\n")


# === NEAR-MISS NEGATIVES: must STAY SILENT (the FP classes 1.4 was scoped out of)

def test_neg_non_integrity_perf_toggle():
    """`cache_skip` is a perf toggle, NOT an integrity check -> not material -> silent."""
    assert not _fires("config.toml", "cache_skip = true\n")


def test_neg_retry_skip_perf():
    assert not _fires("config.toml", "retry_skip = true\n")


def test_neg_dropped_ambiguous_stems_do_not_fire():
    """Broad stems (validat/guard/enforc/seal/complian) were dropped 2026-06-02 — these
    common NON-integrity toggles must NOT block (reviewer-cited FP surface)."""
    for body in ("input_validation_skip = true\n",   # web-form/schema validation
                 "validate_skip = true\n",
                 "guard_skip = true\n",               # UI/route guard
                 "guardrail_skip = true\n",
                 "enforce_skip = true\n",             # rate-limit/style enforcement
                 "enforcement_skip = true\n",
                 "seal_skip = true\n",
                 "compliance_skip = true\n"):
        assert not _fires("config.toml", body), f"dropped-stem FP: {body!r}"


def test_neg_markdown_target_dropped():
    """the same integrity flag in a .md doc -> docs are prose/examples -> silent."""
    assert not _fires("docs/conventions.md", "audit_skip = true\n")


def test_neg_inline_prose_mention():
    """an integrity flag mentioned INLINE in prose (not a standalone line) -> silent."""
    assert not _fires("config.toml", "the audit_skip = true setting is dangerous here\n")


def test_neg_markdown_table_cell():
    """a flag quoted in a markdown table cell -> not a full assignment line -> silent."""
    assert not _fires("notes.toml", "| keeps TP `audit_skip = true` / etc | yes |\n")


def test_neg_commented_out():
    """a commented-out flag is not active suppression -> silent."""
    assert not _fires("config.toml", "# audit_skip = true\n")


def test_neg_makoto_allow_exempts():
    assert not _fires("config.toml", "audit_skip = true  # makoto-allow: app feature, not an integrity check\n")


def test_neg_adr_backlink_exempts():
    assert not _fires("config.toml", 'audit_skip = true\naudit_rationale = "ADR-042"\n')


def test_neg_value_false():
    """`= false` is not a suppression -> silent."""
    assert not _fires("config.toml", "audit_skip = false\n")


def test_neg_wrong_extension():
    """a .py file is not a config target -> silent (handled by target_rx)."""
    assert not _fires("config.py", "audit_skip = true\n")
