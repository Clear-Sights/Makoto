"""tests for makoto/refresh_citations.py — refresh_if_stale(conn)."""
import sqlite3


def _conn_with_config(tmp_path, citations_path_str, mtime_str="-1"):
    """build a fresh sqlite conn with canonical_citations + config tables.

    Uses raw CREATE TABLEs (not init_db) so the test exercises only the
    minimum schema refresh_if_stale needs — no events table churn. Autocommit
    (isolation_level=None) so refresh_if_stale's explicit BEGIN/COMMIT is honored.
    """
    conn = sqlite3.connect(str(tmp_path / "test.db"), isolation_level=None)
    conn.execute("CREATE TABLE canonical_citations (cite TEXT PRIMARY KEY, source TEXT)")
    conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO config VALUES (?, ?)", ["canonical_citations_path", citations_path_str])
    conn.execute("INSERT INTO config VALUES (?, ?)", ["canonical_citations_mtime", mtime_str])
    return conn


def test_refresh_if_stale_noop_when_path_missing(tmp_path):
    """canonical_citations_path doesn't exist -> no rebuild, no error."""
    from makoto.citations import refresh_if_stale
    conn = _conn_with_config(tmp_path, str(tmp_path / "no-such-file.md"))
    refresh_if_stale(conn)
    n = conn.execute("SELECT COUNT(*) FROM canonical_citations").fetchone()[0]
    assert n == 0
    conn.close()


def test_refresh_if_stale_rebuilds_on_mtime_change(tmp_path):
    """on-disk mtime > stored mtime -> DELETE + INSERTs."""
    from makoto.citations import refresh_if_stale
    cit = tmp_path / "CITATIONS.md"
    cit.write_text("Per Smith 2020 and Jones et al. 2021, results hold.\n")
    conn = _conn_with_config(tmp_path, str(cit), mtime_str="-1")  # sentinel: always stale
    refresh_if_stale(conn)
    cites = {r[0] for r in conn.execute("SELECT cite FROM canonical_citations").fetchall()}
    assert "Smith 2020" in cites
    assert any("Jones" in c for c in cites)
    # mtime now updated in config
    stored = conn.execute("SELECT value FROM config WHERE key = 'canonical_citations_mtime'").fetchone()[0]
    assert int(stored) > 0  # real mtime, no longer sentinel
    conn.close()


def test_refresh_if_stale_noop_when_mtime_matches(tmp_path):
    """stored mtime == on-disk mtime -> no rebuild (fast path)."""
    from makoto.citations import refresh_if_stale
    cit = tmp_path / "CITATIONS.md"
    cit.write_text("Smith 2020\n")
    conn = _conn_with_config(tmp_path, str(cit), mtime_str=str(cit.stat().st_mtime_ns))
    # Pre-seed canonical_citations to confirm refresh DOESN'T touch them
    conn.execute("INSERT INTO canonical_citations VALUES ('Stale 1900', 'sentinel')")
    refresh_if_stale(conn)
    n = conn.execute("SELECT COUNT(*) FROM canonical_citations WHERE cite = 'Stale 1900'").fetchone()[0]
    assert n == 1  # sentinel preserved -> refresh was a no-op
    conn.close()


def test_refresh_if_stale_rebuilds_when_mtime_row_missing(tmp_path):
    """canonical_citations_mtime config row absent (mrow=None) -> treated as always-stale,
    rebuild proceeds. The `(mrow and mrow[0])` guard must short-circuit on mrow=None; an OR
    there would subscript None and raise TypeError, never reaching the rebuild."""
    from makoto.citations import refresh_if_stale
    cit = tmp_path / "CITATIONS.md"
    cit.write_text("Per Smith 2020, results hold.\n")
    conn = sqlite3.connect(str(tmp_path / "test.db"), isolation_level=None)
    conn.execute("CREATE TABLE canonical_citations (cite TEXT PRIMARY KEY, source TEXT)")
    conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT)")
    # path row present, but NO canonical_citations_mtime row -> mrow is None at line 104
    conn.execute("INSERT INTO config VALUES (?, ?)", ["canonical_citations_path", str(cit)])
    refresh_if_stale(conn)  # ORIGINAL: rebuilds; MUTANT (mrow or mrow[0]): TypeError
    cites = {r[0] for r in conn.execute("SELECT cite FROM canonical_citations").fetchall()}
    assert "Smith 2020" in cites
    conn.close()


# --- integration: the REAL init_db -> refresh handoff (the install-time path) ----

def test_init_db_then_refresh_populates_canonical(tmp_path):
    """REGRESSION: after a fresh `init_db`, the first `refresh_if_stale` MUST populate
    canonical_citations from CITATIONS.md. init_db formerly seeded the stored mtime to the
    file's CURRENT mtime, so refresh saw 'not stale' and never did the initial rebuild —
    leaving canonical EMPTY, which makes pattern 1.6 (error-level) false-fire on EVERY
    Author-Year citation as phantom. The fix seeds the '-1' always-stale sentinel."""
    from makoto.db import init_db
    from makoto import citations
    state_dir = tmp_path / "makoto_state"
    cit = tmp_path / "CITATIONS.md"
    cit.write_text("Smith 2020\nJones 2019\n")
    init_db(state_dir, cit)
    conn = sqlite3.connect(str(state_dir / "makoto.db"), isolation_level=None)
    citations.refresh_if_stale(conn)          # the FIRST dispatch's refresh
    got = {r[0] for r in conn.execute("SELECT cite FROM canonical_citations").fetchall()}
    assert "Smith 2020" in got and "Jones 2019" in got, \
        f"canonical not populated after init_db+refresh: {got}"
