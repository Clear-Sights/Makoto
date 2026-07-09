"""Conventions delivery — the 3-line installed law + just-in-time fire-time guidance.

Binds the three contract surfaces so none can silently drift:
  (1) the installed CLAUDE.md block stays lean (3 body lines: invariant, makoto-allow, pointer);
  (2) a block decision carries the JIT escape hatch exactly for the checks that honor the
      marker — and never for the ones that refuse it (1.9/1.21/1.22 event-shapes, 1.23 self-mute,
      gate.*);
  (3) _ALLOW_EXEMPT_IDS equals the set DERIVED from each predicate module's source (factory
      scaffold import or a direct makoto_allowed call), so the hint list cannot drift from the
      code that actually implements the exemption;
  (4) the full conventions doc names every active pattern id (catalog-bound materiality).
"""
from __future__ import annotations
import importlib
import inspect
from pathlib import Path

from makoto import _dispatch
from makoto._dispatch import _build_decision, _ALLOW_EXEMPT_IDS
from makoto.core.schema import Finding, load_prechecks

REPO = Path(_dispatch.__file__).resolve().parent

_HATCH = "makoto-allow: <reason>"
_POINTER = "MAKOTO-CONVENTIONS.md"


def _err(pid, hint="fix it"):
    return Finding(pattern_id=pid, file="x.py", line=1, level="error",
                   message=f"{pid} fired", retry_hint=hint)


# --- (1) the installed block is lean -----------------------------------------
def test_installed_block_is_three_lines_and_complete(tmp_path):
    from makoto.install import _install_claude_conventions, _CONV_START, _CONV_END
    cm = tmp_path / "CLAUDE.md"
    _install_claude_conventions(cm)
    text = cm.read_text(encoding="utf-8")
    body = text.split(_CONV_START)[1].split(_CONV_END)[0].strip()
    lines = [l for l in body.splitlines() if l.strip()]
    assert len(lines) == 3, f"installed block must be exactly 3 body lines, got {len(lines)}"
    assert "monoton" in body.lower() and "less checkable" in body, \
        "line 1 must state monotonicity as falsifiability-preservation"
    assert _HATCH in body, "line 2 must state the makoto-allow convention"
    assert "MAKOTO-CONVENTIONS.md" in body, "line 3 must point at the full conventions"


# --- (2) JIT hint at fire time ------------------------------------------------
def test_block_decision_carries_hatch_for_exempting_check():
    d = _build_decision([_err("content.verifier_predicate_weakened")])
    assert d is not None and _HATCH in d["retry_hint"], "exempting check must offer the hatch"
    assert _POINTER in d["retry_hint"], "every block must point at the conventions"
    assert d["retry_hint"].startswith("fix it"), "the pattern's own convention stays first"


def test_block_decision_suppresses_hatch_where_marker_is_refused():
    for pid in ("content.self_mute_guard", "content.unsourced_webfetch", "content.verifier_exit_masking", "content.fabricated_commit_sha", "gate.completion"):
        d = _build_decision([_err(pid)])
        assert d is not None and _HATCH not in d["retry_hint"], \
            f"{pid} refuses the marker — offering the hatch is false guidance"
        assert _POINTER in d["retry_hint"], f"{pid} block must still point at the conventions"


def test_no_error_no_decision_unchanged():
    assert _build_decision([]) is None


# --- (3) the exempt-id set is DERIVED, not asserted ---------------------------
def test_allow_exempt_ids_match_predicate_sources():
    """A pattern belongs in _ALLOW_EXEMPT_IDS iff its predicate module implements the
    exemption: it builds on a factory scaffold (regex_file_predicate / ast_introduced_predicate,
    both of which check makoto_allowed centrally) or calls makoto_allowed directly. Source-derived
    so the JIT hint can never claim an escape hatch the code does not honor — or hide one it does."""
    derived = set()
    for p in load_prechecks():
        if not p.predicate_module:
            continue
        src = inspect.getsource(importlib.import_module(p.predicate_module))
        implements = ("regex_file_predicate" in src or "ast_introduced_predicate" in src
                      or "makoto_allowed" in src)
        refuses = "does NOT exempt" in src
        if implements and not refuses:
            derived.add(p.id)
    assert derived == set(_ALLOW_EXEMPT_IDS), (
        f"drift: derived-from-source {sorted(derived)} != declared {sorted(_ALLOW_EXEMPT_IDS)}")


# --- (4) the full doc names every active pattern (catalog-bound) --------------
def test_conventions_doc_names_every_active_pattern():
    doc = (REPO / "docs" / "MAKOTO-CONVENTIONS.md").read_text(encoding="utf-8")
    missing = [p.id for p in load_prechecks() if p.predicate_module and f"`{p.id}`" not in doc]
    assert not missing, f"conventions doc missing active pattern ids: {missing}"
