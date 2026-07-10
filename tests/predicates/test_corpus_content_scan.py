"""Corpus runner for the content-scan patterns — executes the previously-DEAD TP/TN_1_X corpora.

Patterns 1.1/1.2/1.3/1.4/1.5/1.8 use regex_file_predicate (PreToolUse, target_rx on file_path +
body_rx on content). Their corpus evidence files (tests/corpora/, frontmatter expected_finding/
expected_pass + body) existed but NOTHING executed them. This runner activates them: for each corpus,
build a PreToolUse event with a file_path matching the pattern's target_rx + the body as content, run
the predicate, assert fires-iff-(expected_pass is false). Tests each pattern's DESIGN-INTENT corpus
(the project-context case it should/shouldn't catch) — independent of the global-deployment FP question.

KNOWN PATTERN BUGS found by this runner 2026-05-29 (the corpora are CORRECT; the patterns disagree) —
marked xfail(strict) so a future fix turns xfail→xpass and FORCES removing the marker:
  - TP_1_5 (1.5 FN): misses `[x] <task> DEFERRED` (regex needs `[x]`+ws+`DEFERRED` contiguous) — the
    FN may be the CORRECT no-FP-vs-FN choice (a widen reintroduces a prose-FP; see ledger).
  FIXED 2026-05-29 (xfail removed): TN_1_4 (1.4) + TN_1_8 (1.8) — both converted to custom predicates
  with an ADR-backlink exemption (fire iff flag/phrase present AND no `ADR-NNN` ref).
OUT OF SCOPE (separately unit-tested): 1.6 (citation conn) + 2.2 (Stop+history events).
"""
from __future__ import annotations
import glob
import os
import re
import importlib
import pytest
from makoto.core.schema import PreCheck, load_prechecks

# A file_path that matches each content-scan pattern's target_rx (so the gate passes).
_PATH = {
    "content.verifier_predicate_weakened": "constitution/integrity/checks/sample.py",
    "content.integrity_suppression_flag": "sample.toml",
    "content.deferred_checkbox_theater": "docs/pristine-baseline.md",
}
# corpus filename -> xfail reason (pattern disagrees with its own corpus; fix is FP/FN-precision work)
_KNOWN_BUGS = {
    # TN_1_4 / TN_1_8 FIXED 2026-05-29: 1.4/1.8 converted to custom predicates with an ADR-backlink
    # exemption (fire iff flag/phrase present AND no ADR-NNN ref) — they now correctly stay silent.
    "TP_1_5_deferred_checkbox.md": "1.5 FN: misses '[x] <task> DEFERRED' (needs contiguous [x]+ws+DEFERRED); the FN may be the CORRECT no-FP-vs-FN choice (any widen reintroduces a prose-FP) — see ADVERSARY-FINDINGS.md",
}
_CDIR = os.path.join(os.path.dirname(__file__), "..", "corpora")


def _parse(path: str):
    text = open(path).read()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, f"{path}: no frontmatter"
    fm, body = m.group(1), m.group(2)
    expects_fire = re.search(r"expected_pass:\s*false", fm) is not None
    fr = re.search(r"(?:TP|TN)_(\d+)_(\d+)_", os.path.basename(path))
    pid = f"{fr.group(1)}.{fr.group(2)}"
    return pid, expects_fire, body


def _params():
    out = []
    for p in sorted(glob.glob(os.path.join(_CDIR, "T[PN]_1_*.md"))):
        name = os.path.basename(p)
        pid, expects_fire, body = _parse(p)
        if pid not in _PATH:
            continue  # 1.6 needs a citation conn — separately unit-tested
        marks = [pytest.mark.xfail(reason=_KNOWN_BUGS[name], strict=True)] if name in _KNOWN_BUGS else []
        out.append(pytest.param(name, pid, expects_fire, body, marks=marks, id=name))
    return out


@pytest.mark.parametrize("name,pid,expects_fire,body", _params())
def test_content_scan_corpus(name, pid, expects_fire, body):
    # SPEC-5: prechecks now live in the flat makoto.checks package under descriptive names, not a
    # name derivable from the pattern id -- resolve via the real catalog's predicate_module.
    _mod_path = next(p.predicate_module for p in load_prechecks() if p.id == pid)
    mod = importlib.import_module(_mod_path)
    pat = PreCheck(id=pid, fire_level="error", description="corpus", retry_hint="x")
    evt = {"hook_event_name": "PreToolUse", "tool_input": {"file_path": _PATH[pid], "content": body}}
    f = mod.predicate(current_event=evt, history=[], pattern=pat)
    if expects_fire:
        assert f is not None, f"{name}: expected the pattern to FIRE, got None"
    else:
        assert f is None, f"{name}: expected SILENT, got a Finding: {getattr(f, 'message', f)}"
