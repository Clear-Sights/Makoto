"""PREVENTIVE-at-PreToolUse precheck write.thrash_revert (CANON-PORT-1) — flag a Write that REVERTS
a file back to a byte-identical copy of an earlier whole-file content this session (an A->B->A
oscillation) at PreToolUse time.

WHAT IT FIRES ON: the about-to-execute Write carries `content` byte-identical to an EARLIER
whole-file Write of the SAME `file_path` in this session's history, with at least one INTERVENING
whole-file Write of DIFFERENT content to that path between them (A -> B -> now-A). That is a
self-revert that churns the file with no net progress.

WHY WHOLE-FILE Write.content ONLY (the load-bearing 0-FP narrowing): comparing an Edit `new_string`
FRAGMENT gave 7 corpus FALSE POSITIVES in the sibling canon.oscillate — a short snippet or a
re-inserted import line is not a closed whole-file unit, so two unrelated edits sharing a fragment
look like a bogus revert. This precheck NEVER compares fragments: a CURRENT Edit/MultiEdit/
NotebookEdit is SILENT, and a PRIOR Edit/MultiEdit/NotebookEdit is not counted as a content unit
(only whole-file Writes are). The compared unit is whole-file `Write.content` exclusively.

Copy-by-shape from the makoto-dev ancestor (rule 5 / FD11), re-homed onto live Makoto: it carries
its OWN whole-file-Write history walker so a PreToolUse precheck does not import the Stop-gate
engine. The ONLY content read is through ByteIdentity (==/len/hash only), so this body CANNOT read
content MEANING — only content IDENTITY. Stdlib only; imports only makoto.schema + makoto.canon."""
from __future__ import annotations

import json
from typing import Optional

from makoto.canon.byte_identity import ByteIdentity
from makoto.schema import Finding, PreCheck


def _prior_whole_file_writes(history, path: str) -> list:
    """Ordered ByteIdentity-wrapped whole-file Write contents to `path` in the session history.
    ONLY tool_name=='Write' rows carrying a `content` key are counted — Edit/MultiEdit/NotebookEdit
    fragments are deliberately excluded (the canon.oscillate 7-FP lesson). Rows are either the
    (id, ts, event_type, cwd, raw_payload_json) tuples _select_recent returns OR dicts with a
    'payload' key (corpus replay). Fail-open: an unparseable / payload-less row is skipped."""
    out: list = []
    for row in history or ():
        if isinstance(row, (tuple, list)) and len(row) > 4:
            raw = row[4]
        elif hasattr(row, "get"):
            raw = row.get("payload")
        else:
            raw = None
        if not raw:
            continue
        try:
            ev = raw if isinstance(raw, dict) else json.loads(raw)
        except Exception:
            continue
        if not isinstance(ev, dict) or ev.get("tool_name") != "Write":
            continue
        inp = ev.get("tool_input") or {}
        if not isinstance(inp, dict) or inp.get("file_path") != path or "content" not in inp:
            continue
        out.append(ByteIdentity(inp.get("content")))
    return out


def predicate(*, current_event: dict, history: list,
              pattern: PreCheck, conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    # Whole-file Write ONLY. A current Edit/MultiEdit/NotebookEdit carries only a fragment, not a
    # closed whole-file unit, so it is never judged here (fragment compares are the FP class).
    if current_event.get("tool_name", "") != "Write":
        return None
    ti = current_event.get("tool_input", {}) or {}
    path = ti.get("file_path", "") or ""
    if not path or "content" not in ti:
        return None                       # no path / no whole-file content -> nothing to revert
    now = ByteIdentity(ti.get("content"))

    prior = _prior_whole_file_writes(history, path)
    # A->B->A: some EARLIER whole-file Write of this path == now (an A), AND at least one whole-file
    # Write of DIFFERENT content (a B) lies AFTER that earlier A. A bare A->A repeat (no intervening
    # different content) is a no-op rewrite, not a revert.
    for i, earlier in enumerate(prior):
        if earlier == now and any(mid != now for mid in prior[i + 1:]):
            return Finding(
                pattern_id=pattern.id,
                file=path,
                line=0,
                level=pattern.fire_level,
                message=(
                    f"row {pattern.id} ({pattern.description}): this Write reverts {path!r} back "
                    f"to a byte-identical copy of an earlier whole-file content after it was "
                    f"changed in between (an A->B->A oscillation) — the edits cancel out with no "
                    f"net progress. Decide which content is correct and write it once."
                ),
                retry_hint=pattern.retry_hint,
                snippet=f"<byte-identical whole-file revert of {path!r}>",
            )
    return None

from makoto.checks._loader import Check as _Check
RETRY_HINT = 'Decide which content is correct and write it once; do not revert to an earlier whole-file version after changing it.'
DESCRIPTION = 'whole-file A->B->A self-revert (no net progress)'

CHECK = _Check(id='event.thrash_revert', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('Write',), retry_hint=RETRY_HINT, description=DESCRIPTION)
