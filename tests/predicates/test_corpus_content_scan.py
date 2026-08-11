"""Corpus runner for the content-scan checks — executes the TP/TN design-intent corpora.

Each corpus file under tests/corpora/ is named `TP_<checkModuleStem>_<slug>.md` /
`TN_<checkModuleStem>_<slug>.md`, where <checkModuleStem> is the makoto/checks/ module the
corpus exercises (the id itself is resolved through the LIVE catalog by predicate_module, so a
renamed check id can never silently orphan its corpora — an unresolvable stem FAILS collection
loudly). For each corpus: build a PreToolUse event with a file_path matching the check's
target surface + the corpus body as content, run the predicate, assert
fires-iff-(expected_pass is false). Tests each check's DESIGN-INTENT corpus (the
project-context case it should/shouldn't catch) — independent of the global-deployment FP
question.

History (2026-05-29, ids as of that date): these corpora existed but NOTHING executed them;
this runner activated them and immediately found pattern bugs (the corpora are CORRECT; the
patterns disagreed) — marked xfail(strict) so a future fix turns xfail→xpass and FORCES
removing the marker:
  - TP_deferredCheckboxTheater (FN): misses `[x] <task> DEFERRED` (regex needs `[x]`+ws+`DEFERRED`
    contiguous) — the FN may be the CORRECT no-FP-vs-FN choice (a widen reintroduces a prose-FP;
    see ledger).
  FIXED 2026-05-29 (xfail removed): TN_integritySuppressionFlag + the env-gated-audit TN — both
  converted to custom predicates with an ADR-backlink exemption (fire iff flag/phrase present
  AND no `ADR-NNN` ref).
phantomCitation is OUT OF SCOPE here (needs a live citation DB conn) — separately unit-tested.
"""
from __future__ import annotations
import glob
import os
import re
import importlib
import pytest
from makoto.core.schema import PreCheck, load_prechecks

# A file_path that matches each content-scan check's target_rx (so the gate passes).
_PATH = {
    "content.verifier_predicate_weakened": "constitution/integrity/checks/sample.py",
    "content.integrity_suppression_flag": "sample.toml",
    "content.deferred_checkbox_theater": "docs/pristine-baseline.md",
}
# checks whose corpora need infrastructure this runner does not build — each MUST name where
# it IS tested, so a skip is never silent coverage loss.
_OUT_OF_SCOPE = {
    "content.phantom_citation": "needs a live citation DB conn — tests/test_phantom_citation_scope.py + tests/test_citations.py",
}
# corpus filename -> xfail reason (check disagrees with its own corpus; fix is FP/FN-precision work)
_KNOWN_BUGS = {
    "TP_deferredCheckboxTheater_deferred_checkbox.md": "deferredCheckboxTheater FN: misses '[x] <task> DEFERRED' (needs contiguous [x]+ws+DEFERRED); the FN may be the CORRECT no-FP-vs-FN choice (any widen reintroduces a prose-FP) — ADVERSARY-FINDINGS, repo history",
}
_CDIR = os.path.join(os.path.dirname(__file__), "..", "corpora")


def _parse(path: str):
    text = open(path).read()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, f"{path}: no frontmatter"
    fm, body = m.group(1), m.group(2)
    expects_fire = re.search(r"expected_pass:\s*false", fm) is not None
    rc = re.search(r'reason_contains:\s*"([^"]+)"', fm)
    reason = rc.group(1) if rc else None
    fr = re.match(r"(?:TP|TN)_([A-Za-z]+)_", os.path.basename(path))
    assert fr, f"{path}: corpus filename must be T[PN]_<checkModuleStem>_<slug>.md"
    return fr.group(1), expects_fire, reason, body


def _params():
    stem_to_id = {p.predicate_module.rsplit(".", 1)[-1]: p.id for p in load_prechecks()}
    # The three exact regex members now share one predicate module. Corpus fixture stems remain
    # the old check-specific labels, so recover their IDs from the table rather than pretending
    # the central module is three differently named files.
    from makoto.checks.agnosticRegex import SPECS
    stem_to_id.update({spec.corpus_stem: spec.id for spec in SPECS})
    out = []
    for p in sorted(glob.glob(os.path.join(_CDIR, "T[PN]_*.md"))):
        name = os.path.basename(p)
        stem, expects_fire, reason, body = _parse(p)
        assert stem in stem_to_id, f"{name}: corpus names no live check module (catalog has: {sorted(stem_to_id)})"
        pid = stem_to_id[stem]
        if pid in _OUT_OF_SCOPE:
            continue
        assert pid in _PATH, f"{name}: check {pid} has no _PATH surface entry (add one, or an _OUT_OF_SCOPE entry naming where it IS tested)"
        marks = [pytest.mark.xfail(reason=_KNOWN_BUGS[name], strict=True)] if name in _KNOWN_BUGS else []
        out.append(pytest.param(name, pid, expects_fire, reason, body, marks=marks, id=name))
    assert out, "corpus runner resolved ZERO corpora — the exact silent-death this runner exists to prevent"
    return out


@pytest.mark.parametrize("name,pid,expects_fire,reason,body", _params())
def test_content_scan_corpus(name, pid, expects_fire, reason, body):
    # checks live in the flat makoto.checks package under descriptive names, not a name
    # derivable from the check id -- resolve via the real catalog's predicate_module.
    _mod_path = next(p.predicate_module for p in load_prechecks() if p.id == pid)
    mod = importlib.import_module(_mod_path)
    pat = PreCheck(id=pid, fire_level="error", description="corpus", retry_hint="x")
    evt = {"hook_event_name": "PreToolUse", "tool_input": {"file_path": _PATH[pid], "content": body}}
    f = mod.predicate(current_event=evt, history=[], pattern=pat)
    if expects_fire:
        assert f is not None, f"{name}: expected the check to FIRE, got None"
        if reason is not None:
            assert reason in f.message, \
                f"{name}: frontmatter reason_contains {reason!r} not in fired message {f.message!r}"
    else:
        assert f is None, f"{name}: expected SILENT, got a Finding: {getattr(f, 'message', f)}"
