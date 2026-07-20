"""content.illusory_interruption_claim predicate — a fabricated "interrupted by user" excuse
(誠: material-not-illusory; same genre as content.illusory_authorship_trailer).

Fires PreToolUse when a tool call would INTRODUCE a claim that the USER interrupted this
session — either in a git commit (Bash `command`) or in written file content (Write / Edit /
MultiEdit introduced text) — matching Claude Code's own synthetic marker text
(`"[Request interrupted by user]"`, `makoto/record/ackblock.py`'s `_SYNTHETIC_MARKERS`) or a
paraphrase of it ("interrupted by the user", "user interrupted"). That marker is HARNESS-
SYNTHESIZED, host-written, never model-written (see ackblock.py's own spoof-proof-attribution
note) — so an agent citing it as an excuse for incomplete/abandoned work, when no such
interruption is anywhere in this session's own recorded history, is presenting a fabricated
event the same way content.fabricated_commit_sha catches a hallucinated SHA: a claim dressed up
as evidence, with no real event behind it.

Grounded, not over-broad: if this session's OWN history actually carries a genuine
`tool_response.interrupted == true` row, the claim is TRUE and never fires — this check
widens nothing about what counts as a real interruption; it only catches the claim being
made with NO real interruption anywhere in the record. A bare description of the marker
itself (this module's own docstring, ackblock.py's `_SYNTHETIC_MARKERS` tuple, a test
fixture) is exempted the same way every other check's own documentation is: `makoto-allow:
<reason>`.

Knight-Leveson: stdlib re only.
"""
from __future__ import annotations
import re
from typing import Optional
from makoto.core.schema import Finding, PreCheck
from makoto.substrate.factories import introduced_text, makoto_allowed
from makoto.substrate.io import decode_history_row

# The claim, however it's phrased. Matches the harness's own literal bracketed marker AND
# looser prose paraphrases -- both are the same claim ("the user is why this stopped").
_INTERRUPTION_CLAIM_RX = re.compile(
    r"\[?request\s+interrupted\s+by\s+(?:the\s+)?user\]?"
    r"|\binterrupted\s+by\s+(?:the\s+)?user\b"
    r"|\buser\s+interrupted\b",
    re.IGNORECASE,
)


def _genuine_interruption_in_history(history: list) -> bool:
    """True iff any prior tool event in `history` actually carries a HARNESS-set
    `tool_response.interrupted == true` — the real, non-model-writable signal
    (substrate.io's own documented tool_response shape: stdout/stderr/interrupted/...).
    Fail-open per row: an undecodable row is skipped, never treated as grounding."""
    for row in history or ():
        ev = decode_history_row(row)
        if not isinstance(ev, dict):
            continue
        resp = ev.get("tool_response")
        if isinstance(resp, dict) and resp.get("interrupted") is True:
            return True
    return False


def predicate(*, current_event: dict, history: list,
              pattern: PreCheck, conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    tool_name = current_event.get("tool_name", "") or ""
    tool_input = current_event.get("tool_input", {}) or {}
    text = introduced_text(tool_name, tool_input)
    if not text:
        return None
    if makoto_allowed(text):
        return None  # universal exemption: AI documented this as legitimate (see CLAUDE.md)
    m = _INTERRUPTION_CLAIM_RX.search(text)
    if not m:
        return None
    if _genuine_interruption_in_history(history):
        return None  # a real interruption IS on the record -- the claim is grounded, not illusory
    line_no = text[: m.start()].count("\n") + 1
    snippet = text[max(0, m.start() - 40): m.end() + 40].strip()
    where = tool_input.get("file_path", "") or f"{tool_name or 'tool'} command"
    return Finding(
        pattern_id=pattern.id,
        file=where,
        line=line_no,
        level=pattern.fire_level,
        message=(f"row {pattern.id} ({pattern.description}): matched {m.group(0)!r} at line "
                 f"{line_no} — no genuine interruption is recorded this session"),
        retry_hint=pattern.retry_hint,
        snippet=snippet,
    )


from makoto.substrate._loader import Check as _Check
RETRY_HINT = "Do not write or commit a claim that \"the user interrupted\" this session unless this session's own recorded history actually carries a real harness-set interruption. That marker is host-synthesized, never model-written -- citing it with nothing behind it is a fabricated excuse (same cheat class as content.fabricated_commit_sha). If you truly need the literal string on the record (a test fixture, this policy's own docs), annotate it `makoto-allow: <reason>`."
DESCRIPTION = 'illusory "interrupted by user" claim (no genuine interruption recorded this session) in a commit or written content'

CHECK = _Check(id='content.illusory_interruption_claim', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('interrupted', 'Interrupted', 'INTERRUPTED'), retry_hint=RETRY_HINT, description=DESCRIPTION)
