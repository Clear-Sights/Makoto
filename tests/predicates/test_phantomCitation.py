"""tests for predicates/pattern_1_6.py — phantom citation."""
import sqlite3

from makoto.checks.phantomCitation import predicate
from makoto.schema import PreCheck


_PAT = PreCheck(
    id="content.phantom_citation",
    fire_level="error",
    description="phantom citation — Author-Year not in docs/CITATIONS.md canonical set",
    retry_hint="Add the citation to docs/CITATIONS.md or to [allowlist] citations.",
)


def _evt(file_path: str, content: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_input": {"file_path": file_path, "content": content},
    }


def _conn_with(cites: list[str]):
    """build in-memory sqlite with canonical_citations populated."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE canonical_citations (cite TEXT PRIMARY KEY, source TEXT)")
    for c in cites:
        conn.execute("INSERT INTO canonical_citations VALUES (?, 'test')", [c])
    return conn


def test_pattern_1_6_fires_on_phantom_citation():
    """citation not in canonical set -> Finding."""
    conn = _conn_with(["Smith 2020"])  # Smith canonical, Jones is phantom
    ev = _evt("/tmp/notes.md", "Per Jones 2021, the result holds.")
    f = predicate(current_event=ev, history=[], pattern=_PAT, conn=conn)
    assert f is not None
    assert f.pattern_id == "content.phantom_citation"
    assert "Jones 2021" in f.message
    conn.close()


def test_pattern_1_6_passes_when_in_canonical():
    """citation in canonical set -> None."""
    conn = _conn_with(["Smith 2020"])
    ev = _evt("/tmp/notes.md", "Per Smith 2020, the result holds.")
    assert predicate(current_event=ev, history=[], pattern=_PAT, conn=conn) is None
    conn.close()


def test_pattern_1_6_no_citations_passes():
    """content with no Author-Year patterns -> None."""
    conn = _conn_with([])
    ev = _evt("/tmp/notes.md", "Plain prose with no citations.")
    assert predicate(current_event=ev, history=[], pattern=_PAT, conn=conn) is None
    conn.close()


def test_pattern_1_6_skips_citations_md_itself():
    """docs/CITATIONS.md is the canonical source — don't gate it on itself."""
    conn = _conn_with(["Smith 2020"])
    ev = _evt("docs/CITATIONS.md", "Per Jones 2021, ...")
    assert predicate(current_event=ev, history=[], pattern=_PAT, conn=conn) is None
    conn.close()


def test_pattern_1_6_no_conn_fails_open():
    """no conn passed -> None (don't gate when DB unavailable)."""
    ev = _evt("/tmp/notes.md", "Per Jones 2021, ...")
    assert predicate(current_event=ev, history=[], pattern=_PAT, conn=None) is None


def test_pattern_1_6_non_md_file_returns_none():
    """non-.md file_path returns None."""
    conn = _conn_with(["Smith 2020"])
    ev = _evt("/tmp/code.py", "# Jones 2021 reference")
    assert predicate(current_event=ev, history=[], pattern=_PAT, conn=conn) is None
    conn.close()
