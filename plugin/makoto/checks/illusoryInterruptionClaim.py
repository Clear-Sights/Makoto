"""content.illusory_interruption_claim predicate — a fabricated "interrupted by user" excuse
(誠: material-not-illusory; same genre as content.illusory_authorship_trailer).

Fires PreToolUse when a tool call would INTRODUCE a claim that the USER interrupted this
session — either in a git commit (Bash `command`) or in written file content (Write / Edit /
MultiEdit introduced text) — matching Claude Code's own synthetic marker text
(`"[Request interrupted by user]"`, `makoto/state/ledger.py`'s `_SYNTHETIC_MARKERS`) or a
paraphrase of it ("interrupted by the user", "user interrupted"). That marker is HARNESS-
SYNTHESIZED, host-written, never model-written (see `makoto/state/ledger.py`'s own
`_is_genuine_user_turn` spoof-proof-attribution note) — so an agent citing it as an excuse
for incomplete/abandoned work, when no such interruption appears in this session's RECENT
recorded tool history (the veto reads `dispatch._select_recent`'s bounded ~1h window, pruned
by `_prune_old_events` — never the whole session), is presenting a fabricated event the same way
content.fabricated_commit_sha catches a hallucinated SHA: a claim dressed up as evidence,
with no real event behind it.

Grounded, not over-broad: if this session's OWN history actually carries a genuine
`tool_response.interrupted == true` row or a PostToolUseFailure `is_interrupt == true` terminal,
the claim is TRUE and never fires — this check widens nothing about what counts as a real
interruption; it only catches the claim being made with NO real interruption anywhere in the
record. A bare description of the marker itself (this module's own docstring, that same
`_SYNTHETIC_MARKERS` tuple, a test fixture) is exempted the same way every other check's own
documentation is: `makoto-allow: <reason>`.

Knight-Leveson: stdlib re only.

Built on `kit.introduced_regex_predicate` — the shared scaffold this check and
content.illusory_authorship_trailer both need (scan ANY tool's introduced text, not just a
file-path-gated Write/Edit body), called here WITH `grounded_in_history` — this check's own
history-grounding veto. See that factory's docstring for how `tests/test_check_law_tests.py`
derives PATTERN_MATCH vs. CLAIM_VS_HISTORY from the presence of that keyword at this call site.
"""
from __future__ import annotations
import re
from makoto.kit import decode_history_event, introduced_regex_predicate

# The claim, however it's phrased. Matches the harness's own literal bracketed marker AND
# looser prose paraphrases -- both are the same claim ("the user is why this stopped").
_INTERRUPTION_CLAIM_RX = re.compile(
    r"\[?request\s+interrupted\s+by\s+(?:the\s+)?user\]?"
    r"|\binterrupted\s+by\s+(?:the\s+)?user\b"
    r"|\buser\s+interrupted\b",
    re.IGNORECASE,
)


def _genuine_interruption_in_history(history: list) -> bool:
    """True iff any prior tool event in `history` actually carries a HARNESS-set truthy
    `tool_response.interrupted` or PostToolUseFailure `is_interrupt` — real, non-model-writable
    signals, normalized with `bool(...)` exactly as kit.failure_terminal_result normalizes the
    same fields (a host emitting `1` for true must ground the same fact). Fail-open per row: an
    undecodable row is skipped, never treated as grounding — tests/predicates/
    test_illusoryInterruptionClaim.py pins this deliberately (letting a garbage row GROUND
    would hand the agent a self-grounding spoof: induce one undecodable row, then claim
    freely). Stated cost: a genuine interruption row that fails to decode cannot ground."""
    for row in history or ():
        ev = decode_history_event(row)
        if not isinstance(ev, dict):
            continue
        # INCLUDE the failed-terminal spelling: an interrupted failure grounds the same fact.
        if (ev.get("hook_event_name") == "PostToolUseFailure"
                and bool(ev.get("is_interrupt"))):
            return True
        resp = ev.get("tool_response")
        if isinstance(resp, dict) and bool(resp.get("interrupted")):
            return True
    return False


predicate = introduced_regex_predicate(
    body_rx=_INTERRUPTION_CLAIM_RX,
    grounded_in_history=_genuine_interruption_in_history,
    # The suffix states exactly what was checked: the dispatcher's RECENT event window
    # (dispatch._select_recent, ~1h, pruned) — not "this session", which the veto never reads
    # in full and cannot certify an absence over.
    veto_suffix=(" — no genuine interruption appears in this session's recent recorded"
                 " tool history (the dispatcher's bounded event window)"),
)


from makoto.registry import Check as _Check
RETRY_HINT = "Do not write or commit a claim that \"the user interrupted\" this session unless this session's own recorded history actually carries a real harness-set interruption. That marker is host-synthesized, never model-written -- citing it with nothing behind it is a fabricated excuse (same cheat class as content.fabricated_commit_sha). If you truly need the literal string on the record (a test fixture, this policy's own docs), annotate it `makoto-allow: <reason>`."
DESCRIPTION = 'illusory "interrupted by user" claim (no genuine interruption recorded this session) in a commit or written content'

# keywords: dispatch._keyword_hit is a CASE-SENSITIVE substring prefilter over the raw payload,
# gating whether this predicate runs at all, while _INTERRUPTION_CLAIM_RX is re.IGNORECASE — any
# finite enumeration of word casings leaves regex-matching payloads unevaluated (e.g.
# 'iNTERRUPTED': absence read as green). Every alternative of the regex contains the letter
# 'u' ('user'/'interrupted'), so ('u', 'U') is the case-independent literal cover that makes the
# prefilter a true superset of the regex; the regex itself remains the actual filter.
CHECK = _Check(id='content.illusory_interruption_claim', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('u', 'U'), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "history", "pattern", "conn"}), tests="CLAIM_VS_HISTORY")
