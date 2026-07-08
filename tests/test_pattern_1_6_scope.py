"""pattern 1.6 — the allowlist only governs its OWN project tree.

The canonical_citations allowlist is loaded from one CITATIONS.md (config canonical_citations_path).
It is only valid to enforce for writes inside that project; applied globally it false-fires on every
legitimate Author-Year citation in any other repo (the failure surfaced once makoto ran globally).
These pin: fires inside the governed tree, silent outside it, and silent when the root is unknown is
NOT the contract — unknown root preserves the prior (global) behavior so the check is never silently
disabled.
"""
import sqlite3

import pytest

from makoto.db import init_db
from makoto.citations import refresh_if_stale
from makoto.checks.phantomCitation import predicate, _governed_root
from makoto.schema import load_prechecks

_PAT = {p.id: p for p in load_prechecks()}["content.phantom_citation"]
_PHANTOM = "See (Russo et al. 2018) for the method."   # a real paper, NOT in makoto's allowlist


@pytest.fixture
def conn(tmp_path):
    # governed project root == tmp_path; CITATIONS.md at tmp_path/CITATIONS.md
    cit = tmp_path / "CITATIONS.md"
    cit.write_text("Knight 1986\nLeveson 1993\n")
    init_db(tmp_path / "state", cit)
    c = sqlite3.connect(str(tmp_path / "state" / "makoto.db"), isolation_level=None)
    refresh_if_stale(c)
    return c


def _fire(conn, fp, cwd):
    ev = {"hook_event_name": "PreToolUse", "tool_name": "Write",
          "tool_input": {"file_path": fp, "content": _PHANTOM}, "cwd": cwd}
    return predicate(current_event=ev, history=[], pattern=_PAT, conn=conn) is not None


def test_fires_inside_governed_tree(conn, tmp_path):
    assert _fire(conn, str(tmp_path / "docs" / "notes.md"), str(tmp_path)) is True


def test_silent_outside_governed_tree(conn, tmp_path):
    # an unrelated project that never adopted this CITATIONS.md
    assert _fire(conn, "/some/other/project/readme.md", "/some/other/project") is False


def test_silent_for_relative_path_resolved_into_foreign_cwd(conn):
    assert _fire(conn, "readme.md", "/some/other/project") is False


def test_governed_root_strips_docs_dir(conn, tmp_path):
    # CITATIONS.md at <root>/docs/CITATIONS.md must yield <root>, not <root>/docs
    cit = tmp_path / "docs" / "CITATIONS.md"
    cit.parent.mkdir(parents=True, exist_ok=True)
    cit.write_text("Knight 1986\n")
    init_db(tmp_path / "s2", cit)
    c = sqlite3.connect(str(tmp_path / "s2" / "makoto.db"), isolation_level=None)
    assert _governed_root(c) == tmp_path


def test_unknown_root_preserves_global_behavior(conn):
    # if the config path row is gone, the check must NOT silently disable -> still fires
    conn.execute("DELETE FROM config WHERE key='canonical_citations_path'")
    assert _fire(conn, "/anywhere/x.md", "/anywhere") is True
