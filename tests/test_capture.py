"""tests for makoto.citations.capture — PostToolUse citation capture (1.0.5)."""
import sqlite3


def _conn_with_canonical_citations():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE canonical_citations (cite TEXT PRIMARY KEY, source TEXT)")
    return conn


def test_capture_allowlisted_tool_inserts_cites():
    """research tool + response containing Author-Year strings -> rows inserted."""
    from makoto.citations import capture
    conn = _conn_with_canonical_citations()
    response = "Per Vaswani 2017 and Devlin 2019, transformers are good. Smith et al. 2020."
    n = capture(conn, "WebSearch", response)
    assert n >= 3
    cites = {r[0] for r in conn.execute("SELECT cite FROM canonical_citations").fetchall()}
    assert "Vaswani 2017" in cites
    assert "Devlin 2019" in cites
    assert any("Smith" in c for c in cites)
    conn.close()


def test_capture_non_allowlisted_tool_noop():
    """non-research tool -> no inserts."""
    from makoto.citations import capture
    conn = _conn_with_canonical_citations()
    n = capture(conn, "Bash", "Vaswani 2017 was a great paper")
    assert n == 0
    assert conn.execute("SELECT COUNT(*) FROM canonical_citations").fetchone()[0] == 0
    conn.close()


def test_capture_empty_response_noop():
    """empty tool_response -> no inserts, no exception."""
    from makoto.citations import capture
    conn = _conn_with_canonical_citations()
    assert capture(conn, "WebSearch", "") == 0
    conn.close()


def test_capture_no_cites_in_response_noop():
    """response with no citation patterns -> 0 inserts."""
    from makoto.citations import capture
    conn = _conn_with_canonical_citations()
    assert capture(conn, "WebSearch", "hello world, no cites here") == 0
    conn.close()


def test_capture_dedup_on_conflict():
    """same cite twice -> only one row (ON CONFLICT DO NOTHING)."""
    from makoto.citations import capture
    conn = _conn_with_canonical_citations()
    capture(conn, "WebSearch", "Vaswani 2017 here")
    capture(conn, "WebSearch", "Vaswani 2017 again")
    n = conn.execute("SELECT COUNT(*) FROM canonical_citations WHERE cite = 'Vaswani 2017'").fetchone()[0]
    assert n == 1
    conn.close()


def test_capture_stopword_filter_applied():
    """1.6 stopword filter applies to capture too — 'Saved 2026' / 'The 2023' not captured."""
    from makoto.citations import capture
    conn = _conn_with_canonical_citations()
    response = "Saved 2026-01-01. The 2023 release shipped. From 2020 we had Smith 2020."
    capture(conn, "WebSearch", response)
    cites = {r[0] for r in conn.execute("SELECT cite FROM canonical_citations").fetchall()}
    assert "Saved 2026" not in cites
    assert "The 2023" not in cites
    assert "From 2020" not in cites
    assert "Smith 2020" in cites
    conn.close()


def test_capture_source_tagging():
    """captured rows get source = 'research_capture:<tool_name>'."""
    from makoto.citations import capture
    conn = _conn_with_canonical_citations()
    capture(conn, "WebSearch", "Vaswani 2017 here")
    src = conn.execute("SELECT source FROM canonical_citations WHERE cite = 'Vaswani 2017'").fetchone()[0]
    assert src == "research_capture:WebSearch"
    conn.close()
