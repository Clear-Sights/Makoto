"""Citation machinery — keep `canonical_citations` in sync with reality.

Two cooperating concerns over one canonical citation shape:

  - extract_citations(text): the lowest-level primitive — Author-Year strings in text
        -> (cite, line, snippet), stopword- and ISO-date-filtered. pattern-1.6 calls it.
  - refresh_if_stale(conn): when docs/CITATIONS.md's mtime differs from the stored
        mtime, atomically rebuild canonical_citations from the file.

All use the single canonical vocab._CITATION_RX, so extraction, the on-disk refresh, and
pattern-1.6 validation all agree on what a citation looks like byte-for-byte. stdlib only
(os, pathlib); the sqlite3 conn is passed in.
"""
from __future__ import annotations
import os
import re
from pathlib import Path

from makoto.vocab import _CITATION_RX, _CITATION_AUTHOR_STOPWORDS

# Extraction and canonical rebuild share this whitespace normalization.
_WS_RUN_RX = re.compile(r"\s+")


# --- extract: text -> [(cite, line, snippet)] for pattern-1.6 validation -----------

def extract_citations(text: str) -> list[tuple[str, int, str]]:
    """extract Author-Year citations from text.

    Returns list of (cite_string, line_number, snippet). cite_string is the
    full match including any 'et al.'; line_number is 1-indexed; snippet is
    up to 40 chars of context on each side of the match.

    Filters out matches where the "author" position is a known English stopword
    (The, From, Per, Saved, ...): this exact shape caused a 40% false-positive rate
    in the live audit log.
    """
    out: list[tuple[str, int, str]] = []
    for m in _CITATION_RX.finditer(text):
        author = m.group(1)
        if author in _CITATION_AUTHOR_STOPWORDS:
            continue
        # Skip ISO-date forms: a year directly followed by -DD is a DATE, not a citation
        # (e.g. "Consolidated 2026-05-29", "Released 2025-01"). A real "Author YYYY" cite is
        # never date-suffixed, so TPs (e.g. "Smith 2020 for ...") are unaffected. Reduces the
        # dated-heading FP that fires content.phantom_citation (error-level) on legit docs/changelogs.
        tail = text[m.end():m.end() + 2]
        if len(tail) == 2 and tail[0] == "-" and tail[1].isdigit():
            continue
        cite = _WS_RUN_RX.sub(" ", m.group(0))
        line_no = text[: m.start()].count("\n") + 1
        snip_start = max(0, m.start() - 40)
        snip_end = min(len(text), m.end() + 40)
        snippet = text[snip_start:snip_end]
        out.append((cite, line_no, snippet))
    return out


# --- refresh: docs/CITATIONS.md (on mtime change) -> rebuilt canonical_citations --

def refresh_if_stale(conn) -> None:
    """if docs/CITATIONS.md mtime differs from stored mtime, rebuild canonical_citations.

    Called by dispatch.py after the sqlite connect, before any predicate runs. Single
    source of truth: both the path and the stored mtime live in the `config` table.
    Atomic rebuild via BEGIN/DELETE/INSERTs/COMMIT (the connection opens in autocommit
    mode, isolation_level=None). No-op when the path is unset, missing, unreadable
    (not UTF-8, a directory, permissions), or mtime is unchanged — an
    unreadable-but-present user-editable data file must degrade to "canonical
    untouched", never raise into dispatch's blanket handler, which would loud-allow
    the whole event on every invocation. A corrupt stored mtime reads as stale, so the
    rebuild self-heals it.
    """
    row = conn.execute(
        "SELECT value FROM config WHERE key = 'canonical_citations_path'"
    ).fetchone()
    if row is None:
        return
    cfg_path = row[0]
    try:
        on_disk_mtime = os.stat(cfg_path).st_mtime_ns
    except (OSError, TypeError, ValueError):
        return  # path missing/unset/undecodable — canonical_citations untouched
    mrow = conn.execute(
        "SELECT value FROM config WHERE key = 'canonical_citations_mtime'"
    ).fetchone()
    try:
        stored = int(mrow[0]) if (mrow and mrow[0]) else -1
    except (TypeError, ValueError):
        stored = -1  # corrupt stored mtime -> stale; the rebuild below re-persists it
    if on_disk_mtime == stored:
        return  # fast path — no rebuild
    # Read BEFORE the transaction: an unreadable file is the missing-file case, not a DB fault.
    try:
        text = Path(cfg_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, TypeError, ValueError):
        return  # present but unreadable — canonical_citations untouched
    conn.execute("BEGIN")
    try:
        _rebuild_canonical(conn, text)
        # INSERT OR REPLACE, not a bare UPDATE: when the mtime key is absent (stored == -1) a
        # bare UPDATE affects zero rows, the fast path never engages, and every dispatch
        # re-runs the full write transaction forever.
        conn.execute(
            "INSERT OR REPLACE INTO config(key, value) VALUES ('canonical_citations_mtime', ?)",
            [str(on_disk_mtime)],
        )
        conn.execute("COMMIT")
    except Exception:
        # Suppressing guard: when SQLite already auto-rolled back (SQLITE_FULL / SQLITE_IOERR)
        # an explicit ROLLBACK raises and would replace the real cause in the emitted fact.
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise


def _rebuild_canonical(conn, text: str) -> None:
    """DELETE FROM canonical_citations + INSERT extracted cites. Caller manages txn.

    Extraction IS extract_citations — the same stopword + ISO-date filters and the same
    whitespace fold — so the canonical set and pattern-1.6 validation agree byte-for-byte.
    A raw-regex rebuild applying neither filter would mint a canonical row from a
    maintenance date line ('- Reviewed 2024-03-01' -> 'Reviewed 2024'), granting a PASS
    to a citation nobody listed, plus unreachable junk rows."""
    # The set dedups: `cite` is the PRIMARY KEY and the INSERT below has no OR IGNORE.
    rows = list({(cite,) for cite, _line, _snippet in extract_citations(text)})
    conn.execute("DELETE FROM canonical_citations")
    if rows:
        conn.executemany(
            "INSERT INTO canonical_citations(cite, source) VALUES (?, 'CITATIONS.md')",
            rows,
        )
