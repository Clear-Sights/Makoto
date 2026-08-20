"""content.phantom_citation predicate — phantom citation (Author-Year not in canonical set).

Spec §5.6. Reads tool_input.content (NOT disk), extracts Author-Year strings
via citations.extract_citations, queries the canonical_citations table via the
dispatcher-passed conn. Fail-open if conn is None (Knight-Leveson: a missing
DB must not block agent work).
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional
from makoto.vocab import Finding
from makoto.registry import Check
from makoto.kit import _record_exemption, makoto_allow_reason, makoto_allowed, scan_target_content
from makoto.state.citations import extract_citations


_TARGET_RX = re.compile(r"\.md$")

# Membership is judged on the whitespace-FOLDED citation string: _CITATION_RX's `\s+` matches a
# newline or a run of spaces, so "Kahneman  2011" / a line-wrapped "Kahneman\n2011" is the SAME
# canonical citation as "Kahneman 2011" — byte-equality against the single-space canonical row
# denied those variants on a false fact.
_WS_RUN_RX = re.compile(r"\s+")


def _fold_ws(cite: str) -> str:
    return _WS_RUN_RX.sub(" ", cite)


def _canonical_path(conn) -> Optional[str]:
    """The configured canonical_citations_path, or None when unknown (missing config table/row)."""
    try:
        row = conn.execute("SELECT value FROM config WHERE key='canonical_citations_path'").fetchone()
    except Exception:
        return None   # no config table/row -> unknown
    if not row or not row[0]:
        return None
    return row[0]


def _governed_root(conn) -> Optional[Path]:
    """The project tree the loaded allowlist actually governs — the repo that owns the
    canonical_citations_path CITATIONS.md. The allowlist is project-specific (makoto's own cites),
    so it is only VALID to enforce for writes inside that tree; applied globally it false-fires on
    every legitimate Author-Year citation in any OTHER project. Returns None if the path is unknown
    (then we fall through to the prior global behavior rather than silently disabling the check)."""
    path = _canonical_path(conn)
    if path is None:
        return None
    d = Path(path).parent
    # CITATIONS.md conventionally lives at <root>/CITATIONS.md or <root>/docs/CITATIONS.md.
    return d.parent if d.name in ("docs", "doc") else d


def _within_governed_tree(fp: str, cwd: str, root: Optional[Path]) -> bool:
    """True iff the write target resolves inside the allowlist-governing tree (or the root is
    unknown -> preserve prior behavior). fp may be relative; resolve it against the event cwd."""
    if root is None:
        return True
    target = Path(fp)
    if not target.is_absolute():
        if not cwd:
            return True   # relative path + unknown cwd -> can't place it -> preserve the check
        target = Path(cwd) / fp
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


# jscpd flags this as a clone against fabricatedCommitSha.py; the shared span is the fixed
# dispatcher entrypoint signature (a structural contract, not extractable logic), and the two
# bodies do unrelated things. Not to be "deduped" -- see
# docs/adr/0042-phantom-citation-jscpd-clone-flag.md for the verification record.
def predicate(*, current_event: dict, history: list, pattern: Check,
              conn=None) -> Optional[Finding]:
    """fire on first Author-Year string not present in canonical_citations."""
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    # `or {}`: the host may send `tool_input: null`; sibling checks (claimedShippedAbsent,
    # writeThrashRevert, ...) already no-op on it instead of raising into the dispatcher's
    # error row.
    tool_input = current_event.get("tool_input") or {}
    fp = tool_input.get("file_path", "")
    if not _TARGET_RX.search(fp) or fp.endswith("docs/CITATIONS.md"):
        return None
    if conn is None:
        # Fail-open: predicate requires DB; missing conn -> no decision.
        return None
    # Self-exemption by CONFIGURED path, not only the conventional docs/ suffix: an install whose
    # canonical file lives at <root>/CITATIONS.md must be able to edit its own allowlist — the
    # DENY otherwise tells the author to add the entry to the very file the write is adding it to.
    canonical_path = _canonical_path(conn)
    if canonical_path:
        cwd = current_event.get("cwd", "")
        target = Path(fp)
        if not target.is_absolute() and cwd:
            target = Path(cwd) / fp
        try:
            if target.resolve() == Path(canonical_path).resolve():
                return None
        except OSError:
            pass
    # The allowlist only validly governs its own project; a write outside that tree (another repo
    # that never adopted this CITATIONS.md) must not be judged against it, or every real citation
    # there false-fires now that makoto runs globally.
    if not _within_governed_tree(fp, current_event.get("cwd", ""), _governed_root(conn)):
        return None
    content = scan_target_content(tool_input)
    cites = extract_citations(content)
    if not cites:
        return None
    # An UNPOPULATED allowlist is indistinguishable from "every citation is phantom" only if we
    # let it deny: the same fail-open reasoning as `conn is None` applies (Knight-Leveson — a
    # missing/never-refreshed CITATIONS.md, e.g. moved after init so refresh_if_stale no-ops,
    # must not block agent work by denying every citation on a false fact).
    if conn.execute("SELECT 1 FROM canonical_citations LIMIT 1").fetchone() is None:
        return None
    # One parameterized lookup against canonical_citations, on the whitespace-folded strings
    # (see _fold_ws: a canonical citation's whitespace variant is still canonical).
    placeholders = ", ".join(["?"] * len(cites))
    canonical_rows = conn.execute(
        f"SELECT cite FROM canonical_citations WHERE cite IN ({placeholders})",
        [_fold_ws(c[0]) for c in cites]
    ).fetchall()
    canonical_set = {row[0] for row in canonical_rows}
    phantom = next((c for c in cites if _fold_ws(c[0]) not in canonical_set), None)
    if phantom is None:
        return None
    if makoto_allowed(content):
        # DETECT-THEN-EXEMPT (R5b, matching kit._exempt_or_finding/introduced_regex_predicate):
        # the phantom is real, the marker suppresses the Finding, and the suppression is
        # RECORDED — the old order (exempt before detection) left no exemption row, so the
        # escape valve was invisible to review.
        _record_exemption(
            current_event, conn, pattern_id=pattern.id, file=fp, line=phantom[1],
            reason=makoto_allow_reason(content) or "", snippet=phantom[2].strip())
        return None  # AI documented these citations as legitimate (see CLAUDE.md)
    cite_str, line_no, snippet = phantom
    return Finding(
        pattern_id=pattern.id,
        file=fp,
        line=line_no,
        level="error",  # Pre-tier is invariantly BLOCK; Check has no fire_level (test_pre_tier_block_invariant.py)
        message=f"row {pattern.id} ({pattern.description}): '{cite_str}' not in canonical CITATIONS.md set",
        retry_hint=pattern.retry_hint,
        snippet=snippet,
    )


from makoto.registry import Check as _Check
RETRY_HINT = "Add the citation as an Author-Year entry to the canonical CITATIONS.md this install wired (the `canonical_citations_path` config row — the packaged makoto/docs/CITATIONS.md by default)."
DESCRIPTION = 'phantom citation — Author-Year not in the canonical CITATIONS.md set'

# keywords: dispatch._keyword_hit is a case-sensitive raw-substring prefilter that GATES whether
# this predicate runs at all, so it must be a SUPERSET of what _CITATION_RX can match. Every
# citation carries a `\d{4}` year (any year — 'Ricardo 1817' is as phantom as 'Smith 2020', and
# the regex's `\s+` separator may be a newline, which json-escapes so ' 19'-style literals miss
# it); the only casing/escape-independent literal cover is "the payload contains a digit".
CHECK = _Check(id='content.phantom_citation', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=tuple("0123456789"), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="PATTERN_MATCH")
