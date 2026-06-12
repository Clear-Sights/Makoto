"""Citation machinery — keep `canonical_citations` in sync with reality.

Three cooperating concerns over one canonical citation shape (the table pattern-1.6
validates against):

  - extract_citations(text): the lowest-level primitive — Author-Year strings in text
        -> (cite, line, snippet), stopword- and ISO-date-filtered. pattern-1.6 calls it.
  - capture(conn, tool, response): on PostToolUse for a research-class tool,
        extract Author-Year strings from the tool_response and INSERT new ones.
  - refresh_if_stale(conn): when docs/CITATIONS.md's mtime exceeds the stored
        mtime, atomically rebuild canonical_citations from the file.

All use the single canonical lexicons._CITATION_RX, so extraction, capture, the on-disk
refresh, and pattern-1.6 validation all agree on what a citation looks like
byte-for-byte. Knight-Leveson: stdlib only (re, os, pathlib); the sqlite3 conn
is passed in. Spec §5.2 (refresh); v1.0.3 (capture); v1.0.5 (extract stopword/date filter).
"""
from __future__ import annotations
import os
from pathlib import Path

from makoto.lexicons import _CITATION_RX, _CITATION_AUTHOR_STOPWORDS


# --- extract: text -> [(cite, line, snippet)] for pattern-1.6 validation -----------

def extract_citations(text: str) -> list[tuple[str, int, str]]:
    """extract Author-Year citations from text.

    Returns list of (cite_string, line_number, snippet). cite_string is the
    full match including any 'et al.'; line_number is 1-indexed; snippet is
    up to 40 chars of context on each side of the match.

    Filters out matches where the "author" position is a known English
    stopword (The, From, Per, Saved, ...) — added 1.0.5 after the live audit
    log showed 40% FP rate from this exact shape.
    """
    out: list[tuple[str, int, str]] = []
    for m in _CITATION_RX.finditer(text):
        author = m.group(1)
        if author in _CITATION_AUTHOR_STOPWORDS:
            continue
        # Skip ISO-date forms: a year directly followed by -DD is a DATE, not a citation
        # (e.g. "Consolidated 2026-05-29", "Released 2025-01"). A real "Author YYYY" cite is
        # never date-suffixed, so TPs (e.g. "Smith 2020 for ...") are unaffected. Reduces the
        # dated-heading FP that fires pattern 1.6 (error-level) on legit docs/changelogs.
        tail = text[m.end():m.end() + 2]
        if len(tail) == 2 and tail[0] == "-" and tail[1].isdigit():
            continue
        cite = m.group(0)
        line_no = text[: m.start()].count("\n") + 1
        snip_start = max(0, m.start() - 40)
        snip_end = min(len(text), m.end() + 40)
        snippet = text[snip_start:snip_end]
        out.append((cite, line_no, snippet))
    return out


# --- capture: a research tool's tool_response -> new canonical_citations rows ------

# Hardcoded allowlist of research-class tools whose tool_response yields cites.
_RESEARCH_TOOLS = frozenset({
    # Claude Code natives
    "WebFetch", "WebSearch",
    # paper-search MCP
    "mcp__paper-search__search_arxiv",
    "mcp__paper-search__search_pubmed",
    "mcp__paper-search__search_biorxiv",
    "mcp__paper-search__search_medrxiv",
    "mcp__paper-search__search_google_scholar",
    "mcp__paper-search__read_arxiv_paper",
    "mcp__paper-search__read_pubmed_paper",
    "mcp__paper-search__read_biorxiv_paper",
    "mcp__paper-search__read_medrxiv_paper",
    # bio-research
    "mcp__plugin_bio-research_consensus__search",
    "mcp__plugin_bio-research_pubmed__search_articles",
    "mcp__plugin_bio-research_pubmed__get_article_metadata",
    "mcp__plugin_bio-research_pubmed__get_full_text_article",
    # HF papers/docs
    "mcp__32c395a2-46df-4532-b638-59eed523d6fd__paper_search",
    "mcp__32c395a2-46df-4532-b638-59eed523d6fd__hf_doc_search",
    "mcp__32c395a2-46df-4532-b638-59eed523d6fd__hf_doc_fetch",
})


def capture(conn, tool_name: str, tool_response: str) -> int:
    """Extract Author-Year cites from a research tool's response, INSERT new ones.

    Returns the count of (cite, source) row attempts. ON CONFLICT DO NOTHING
    handles dedup at the DB level. No-op for non-research tools or empty
    response or zero matches. Stopword filter applied so 'The 2023' etc.
    don't pollute the canonical set.
    """
    if tool_name not in _RESEARCH_TOOLS:
        return 0
    if not tool_response:
        return 0
    seen = set()
    for m in _CITATION_RX.finditer(tool_response):
        author = m.group(1)
        if author in _CITATION_AUTHOR_STOPWORDS:
            continue
        seen.add(m.group(0).strip())
    if not seen:
        return 0
    src = f"research_capture:{tool_name}"
    rows = [(cite, src) for cite in seen]
    conn.executemany(
        "INSERT INTO canonical_citations(cite, source) VALUES (?, ?) "
        "ON CONFLICT (cite) DO NOTHING",
        rows,
    )
    return len(rows)


# --- refresh: docs/CITATIONS.md (on mtime change) -> rebuilt canonical_citations --

def refresh_if_stale(conn) -> None:
    """if docs/CITATIONS.md mtime exceeds stored mtime, rebuild canonical_citations.

    Spec §5.2. Called by _dispatch.py after the sqlite connect, before any predicate
    runs. Single source of truth: both the path AND the stored mtime live in the
    `config` table (v5 fix #16). Atomic rebuild via BEGIN/DELETE/INSERTs/COMMIT
    (honored because the connection opens in autocommit mode, isolation_level=None).
    No-op when the path is unset, missing, or mtime is unchanged.
    """
    row = conn.execute(
        "SELECT value FROM config WHERE key = 'canonical_citations_path'"
    ).fetchone()
    if row is None:
        return
    cfg_path = row[0]
    try:
        on_disk_mtime = os.stat(cfg_path).st_mtime_ns
    except FileNotFoundError:
        return  # path missing — canonical_citations untouched
    mrow = conn.execute(
        "SELECT value FROM config WHERE key = 'canonical_citations_mtime'"
    ).fetchone()
    stored = int(mrow[0]) if (mrow and mrow[0]) else -1
    if on_disk_mtime == stored:
        return  # fast path — no rebuild
    conn.execute("BEGIN")
    try:
        _rebuild_canonical(conn, cfg_path)
        conn.execute(
            "UPDATE config SET value = ? WHERE key = 'canonical_citations_mtime'",
            [str(on_disk_mtime)],
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _rebuild_canonical(conn, cfg_path: str) -> None:
    """DELETE FROM canonical_citations + INSERT extracted cites. Caller manages txn."""
    text = Path(cfg_path).read_text(encoding="utf-8")
    rows = list({(m.group(0).strip(),) for m in _CITATION_RX.finditer(text)})
    conn.execute("DELETE FROM canonical_citations")
    if rows:
        conn.executemany(
            "INSERT INTO canonical_citations(cite, source) VALUES (?, 'CITATIONS.md')",
            rows,
        )
