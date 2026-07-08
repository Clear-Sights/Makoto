"""Universal `makoto-allow` exemption (2026-05-29) — makes the 6 over-broad content-scan
patterns FP-exemptable EVERYWHERE.

Makoto's bundled CLAUDE.md (written by the installer, docs/MAKOTO-CONVENTIONS.md) teaches the
AI to annotate a LEGITIMATE instance of a flagged shape with `makoto-allow: <reason>`. A
compliant AI thus marks its legitimate cases (no FP), and only UNMARKED (likely-violation)
content fires. This replaces the rejected "origin-project presence-gate" approach: the patterns
stay ACTIVE everywhere, with a universal honest escape valve.

Contract per pattern: the violation TP fires; the SAME content + a `makoto-allow` marker is
exempt (returns None). Makoto targets the AI (which reads the bundled CLAUDE.md), never the user.
"""
from __future__ import annotations
import sqlite3
import tempfile
from pathlib import Path

import pytest

from makoto.schema import PreCheck, load_prechecks


def _evt(file_path: str, content: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_input": {"file_path": file_path, "content": content}}


def _run(pid: str, content: str, file_path: str, level: str, conn=None):
    import importlib
    # SPEC-5: resolve via the real catalog's predicate_module (flat makoto.checks, descriptive
    # names -- no longer derivable from the pattern id).
    _mod_path = next(p.predicate_module for p in load_prechecks() if p.id == pid)
    mod = importlib.import_module(_mod_path)
    pat = PreCheck(id=pid, fire_level=level, description="x", retry_hint="y")
    return mod.predicate(current_event=_evt(file_path, content), history=[], pattern=pat, conn=conn)


# (pattern_id, file_path, violating_content, fire_level)
# 1.2/1.3/1.8 CUT 2026-06-02 (irreducibly FP-prone — see warning-tier-elimination cert). 1.4 scoped
# to the integrity-keyed shape (`audit_skip`); a bare `cache_skip` no longer fires (not an integrity check).
_CASES = [
    ("content.integrity_suppression_flag", "config.toml", "audit_skip = true\n", "error"),
]


@pytest.fixture(scope="module")
def citation_conn():
    tmp = Path(tempfile.mkdtemp())
    cit = tmp / "CITATIONS.md"
    cit.write_text("Smith 2020\n")
    import makoto.db as vdb
    vdb.init_db(tmp / "st", cit)
    conn = sqlite3.connect(str(tmp / "st" / "makoto.db"))
    yield conn
    conn.close()


@pytest.mark.parametrize("pid,fp,content,level", _CASES, ids=[c[0] for c in _CASES])
def test_violation_fires_but_makoto_allow_exempts(pid, fp, content, level):
    assert _run(pid, content, fp, level) is not None, f"{pid}: violation must fire"
    exempted = content.rstrip() + "  # makoto-allow: legitimate for this app\n"
    assert _run(pid, exempted, fp, level) is None, f"{pid}: makoto-allow marker must exempt"


def test_1_6_violation_fires_but_makoto_allow_exempts(citation_conn):
    content = "As shown by Faketon 2019 the result holds.\n"
    assert _run("content.phantom_citation", content, "paper.md", "error", conn=citation_conn) is not None, "1.6 phantom citation must fire"
    exempted = content.rstrip() + "  <!-- makoto-allow: real source, cited from memory -->\n"
    assert _run("content.phantom_citation", exempted, "paper.md", "error", conn=citation_conn) is None, "1.6: makoto-allow must exempt"


def test_makoto_allow_requires_structured_reason():
    from makoto.lib.factories import makoto_allowed
    # structured `makoto-allow: <reason>` exempts (case-insensitive, any comment style)
    assert makoto_allowed("x = 1  # MAKOTO-ALLOW: ok")
    assert makoto_allowed("Makoto-Allow: somewhere")
    assert makoto_allowed("y  <!-- makoto-allow:   real source -->")
    # a BARE marker (no colon, or colon with no reason) no longer exempts — §7.5b
    assert not makoto_allowed("Makoto-Allow somewhere")
    assert not makoto_allowed("x = 1  # makoto-allow")
    assert not makoto_allowed("x = 1  # makoto-allow:")
    assert not makoto_allowed("x = 1  # makoto-allow:   ")
    assert not makoto_allowed("no marker here")
    assert not makoto_allowed("")
