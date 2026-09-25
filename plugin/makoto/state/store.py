"""SQLite(WAL) schema bootstrap — single init_db creates every table makoto needs.

Idempotent: safe to call on a fresh DB or one already initialized. cmd_install
invokes init_db() once per install; the dispatcher never runs DDL beyond the
lazy-init bootstrap in dispatch._ensure_db_initialized.

stdlib `sqlite3` only. No LLM, no HTTP.

Connections open in autocommit mode (`isolation_level=None`) so the explicit
BEGIN/COMMIT/ROLLBACK in citations.refresh_if_stale is honored verbatim rather than
fighting the driver's implicit transaction management. WAL gives concurrent
readers plus a single writer, so parallel hook fires no longer serialize on a
file-level write lock.

Tables (all idempotent via IF NOT EXISTS):
  events              — append-only event log; (session_id, ts) + event_type indexes
  canonical_citations — Author-Year lookup populated by citations.refresh_if_stale
  config              — key/value seed (canonical_citations_path + _mtime)
  ledger              — results/touches keyed by normalized location, latest-wins
  plans               — one declared contract Plan per session, latest-wins whole
"""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path


def _connect(db_path: Path) -> sqlite3.Connection:
    """open makoto.record.db in autocommit WAL mode (the one true connection idiom)."""
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(state_dir: Path, citations_path: Path) -> None:
    """create (or update) <state_dir>/makoto.record.db with every table, idempotently.

    `kind ∈ {count,value,touched}`; `status ∈ {open,discharged,retracted}`.
    config seed rows are UPSERTed on every call (INSERT OR REPLACE) so re-install
    after moving CITATIONS.md does not leave stale path/mtime.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    conn = _connect(state_dir / "makoto.record.db")
    try:
        # One transaction around every DDL statement and the config seeds. In autocommit
        # mode each statement commits separately, so an interruption after the CREATE
        # TABLEs but before the config seeds would leave a DB with tables and no seed
        # rows: phantom-citation then reads "no canonical_citations_path configured" and
        # enforces an empty allowlist globally. BEGIN IMMEDIATE takes the write lock up
        # front so a concurrent init waits (busy_timeout) instead of interleaving.
        conn.execute("BEGIN IMMEDIATE")
        # events — append-only event log
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                cwd        TEXT NOT NULL,
                payload    TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS events_session_ts_idx ON events(session_id, ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS events_type_idx       ON events(event_type)")
        # ts-only index so the rolling-window prune (DELETE WHERE ts < cutoff) is index-assisted;
        # the composite session_ts index above leads with session_id and can't serve a ts-only scan.
        conn.execute("CREATE INDEX IF NOT EXISTS events_ts_idx         ON events(ts)")
        # canonical_citations — Author-Year allowlist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS canonical_citations (
                cite   TEXT PRIMARY KEY,
                source TEXT
            )
        """)
        # config — key/value seed
        conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # ledger — recorded `update`s keyed by normalized location, latest-wins
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ledger (
                key             TEXT PRIMARY KEY,
                value           TEXT,
                kind            TEXT NOT NULL,
                exit            INTEGER,
                source_event_id INTEGER,
                session_id      TEXT,
                ts              TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )
        """)
        # plans — one declared contract Plan per session, latest-wins on the WHOLE plan
        # (declare replaces the whole plan, mark_done+resync persists it again). `rows` is
        # the JSON-encoded list of PlanNode row dicts, in plan (ledger) order.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                session_id TEXT PRIMARY KEY,
                rows       TEXT NOT NULL,
                ts         TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )
        """)
        # Seed the mtime to the "-1" always-stale sentinel, not the file's current mtime.
        # init_db only creates the (empty) canonical_citations table; the first
        # refresh_if_stale populates it from CITATIONS.md. Seeding the real mtime would make
        # refresh see "not stale" and skip that initial rebuild, leaving canonical empty so
        # content.phantom_citation false-fires on every Author-Year citation. -1 guarantees
        # the first refresh rebuilds and records the real mtime, so later dispatches fast-path.
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ["canonical_citations_path", str(citations_path)],
        )
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ["canonical_citations_mtime", "-1"],
        )
        conn.execute("COMMIT")
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass                      # already rolled back / lock lost -- the raise below is the fact
        raise
    finally:
        conn.close()


# =============================================================================================
# Shared state-directory resolution. Reads $MAKOTO_STATE_DIR env var; defaults to
# $HOME/.claude/makoto_state/. Importable by dispatch.py, citations refresh, and tests
# without circular imports (stdlib only).
# =============================================================================================


def _state_dir() -> Path:
    """resolve the canonical state directory.

    $MAKOTO_STATE_DIR overrides; default $HOME/.claude/makoto_state/.
    """
    env = os.environ.get("MAKOTO_STATE_DIR")
    if env:
        configured = Path(env).expanduser()
        # Hook processes run with the target repository as cwd, which can differ between
        # PostToolUse and Stop. A relative override must therefore be anchored independently of
        # cwd or one session is silently split across stores.
        return configured if configured.is_absolute() else Path.home() / configured
    return Path.home() / ".claude" / "makoto_state"
