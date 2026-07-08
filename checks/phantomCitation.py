"""pattern 1.6 predicate — phantom citation (Author-Year not in canonical set).

Spec §5.6. Reads tool_input.content (NOT disk), extracts Author-Year strings
via citations.extract_citations, queries the canonical_citations table via the
dispatcher-passed conn. Fail-open if conn is None (Knight-Leveson: a missing
DB must not block agent work).
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional
from makoto.schema import Finding, PreCheck
from makoto.lib.factories import makoto_allowed, scan_target_content
from makoto.citations import extract_citations


_TARGET_RX = re.compile(r"\.md$")


def _governed_root(conn) -> Optional[Path]:
    """The project tree the loaded allowlist actually governs — the repo that owns the
    canonical_citations_path CITATIONS.md. The allowlist is project-specific (makoto's own cites),
    so it is only VALID to enforce for writes inside that tree; applied globally it false-fires on
    every legitimate Author-Year citation in any OTHER project. Returns None if the path is unknown
    (then we fall through to the prior global behavior rather than silently disabling the check)."""
    try:
        row = conn.execute("SELECT value FROM config WHERE key='canonical_citations_path'").fetchone()
    except Exception:
        return None   # no config table/row -> root unknown -> caller preserves prior behavior
    if not row or not row[0]:
        return None
    d = Path(row[0]).parent
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


def predicate(*, current_event: dict, history: list, pattern: PreCheck,
              conn=None) -> Optional[Finding]:
    """fire on first Author-Year string not present in canonical_citations."""
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    fp = current_event.get("tool_input", {}).get("file_path", "")
    if not _TARGET_RX.search(fp) or fp.endswith("docs/CITATIONS.md"):
        return None
    if conn is None:
        # Fail-open: predicate requires DB; missing conn -> no decision.
        return None
    # The allowlist only validly governs its own project; a write outside that tree (another repo
    # that never adopted this CITATIONS.md) must not be judged against it, or every real citation
    # there false-fires now that makoto runs globally.
    if not _within_governed_tree(fp, current_event.get("cwd", ""), _governed_root(conn)):
        return None
    content = scan_target_content(current_event.get("tool_input", {}))
    if makoto_allowed(content):
        return None  # AI documented these citations as legitimate (see CLAUDE.md)
    cites = extract_citations(content)
    if not cites:
        return None
    # One parameterized lookup against canonical_citations.
    placeholders = ", ".join(["?"] * len(cites))
    canonical_rows = conn.execute(
        f"SELECT cite FROM canonical_citations WHERE cite IN ({placeholders})",
        [c[0] for c in cites]
    ).fetchall()
    canonical_set = {row[0] for row in canonical_rows}
    phantom = [c for c in cites if c[0] not in canonical_set]
    if not phantom:
        return None
    cite_str, line_no, snippet = phantom[0]
    return Finding(
        pattern_id=pattern.id,
        file=fp,
        line=line_no,
        level=pattern.fire_level,
        message=f"row {pattern.id} ({pattern.description}): '{cite_str}' not in canonical CITATIONS.md set",
        retry_hint=pattern.retry_hint,
        snippet=snippet,
    )


from makoto.checks._loader import Check as _Check
RETRY_HINT = "Add the citation to docs/CITATIONS.md as an Author-Year entry."
# FABLE DECISION (2026-07-08): this used to also say "OR add it to the [allowlist] citations
# block in makoto/data/patterns.toml if it's in-flight" -- but nothing ever read that block (a
# genuinely dead feature); an unbuilt escape hatch advertised in a check's own retry_hint is
# itself an illusory word, so the claim was retired rather than built out post-hoc to make it
# retroactively true. See docs/DEFERRED.md for the citation this closed.
DESCRIPTION = 'phantom citation — Author-Year not in docs/CITATIONS.md canonical set'

CHECK = _Check(id='content.phantom_citation', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('et al', ' 19', ' 20'), retry_hint=RETRY_HINT, description=DESCRIPTION)
