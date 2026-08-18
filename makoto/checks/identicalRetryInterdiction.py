"""makoto.checks.identicalRetryInterdiction -- D1 (docs/DEFERRED.md): PreToolUse interdiction of
a byte-identical Bash retry immediately following a DETERMINISTIC failure of the SAME call --
"kills the loop at length 1," the PROACTIVE twin of canon.recur (canonTimeoutRecur.py, which is
reactive at Stop, judging a run of >=2 consecutive identical failing calls after the fact). This
fires BEFORE the redundant call even runs.

Ship bar (two design consultations, docs/DEFERRED.md D1): BLOCK-tier only, and ONLY when
`_failureClassifier.classify_failure` returns a CONFIDENT True (deterministic) for the prior
call's result -- never on a transient failure (a timeout, a 5xx, "still running"), and never on
an uncertain classification. An advisory version was rejected outright (this project's own
deliberate warning-tier-elimination invariant: "a hedge that emits a finding nobody acts on" is
the exact illusory-word shape Makoto exists to catch); a block with a KNOWN transient-retry FP
class would fail the SAME zero-FP admissibility bar the invariant demands. This predicate fires
ONLY on the confident-True side of that bar.

"No intervening state change" is enforced structurally, not by scanning for one: only the
SINGLE MOST RECENT history row is consulted. If anything else happened between the failing call
and now (a different tool call, a file edit, another Bash command), THAT would be the most
recent row instead, and this predicate stays silent -- an intervening action always breaks the
match by construction.
"""
from __future__ import annotations

import json
from typing import Optional

from makoto.kit import classify_failure
from makoto.kit import bash_output_text, decode_history_event
from makoto.vocab import Finding
from makoto.registry import Check


def _canon_input(ti: dict) -> str:
    try:
        return json.dumps(ti, sort_keys=True, default=str)
    except Exception:
        return repr(ti)


def _most_recent_completed_bash_call(history) -> Optional[tuple]:
    """(tool_input, result_text) of the SINGLE MOST RECENT history row, iff that row is a
    settled PostToolUse/PostToolUseFailure Bash call -- else None (a different tool, a Pre row,
    or nothing at all). Failed terminals classify their real top-level error text.

    Decoding is `kit.decode_history_event` -- the canonical row-decode-plus-wrapper-fallback
    step, shared with `canonTimeoutRecur._decode_row`. Sharing it is what keeps this predicate
    and its sibling gate (canon.timeout/canon.recur) reading the SAME rows from the same table
    for the same concept -- including rows whose event type lives only on the WRAPPER column.
    See docs/adr/0039-identical-retry-shared-row-decoder.md for the decision history."""
    rows = list(history or ())
    if not rows:
        return None
    ev = decode_history_event(rows[-1])
    if ev is None or ev.get("tool_name") != "Bash":
        return None
    event_type = ev.get("hook_event_name")
    # INCLUDE failed terminals: this check reasons about the immediately prior failed attempt.
    if event_type not in ("PostToolUse", "PostToolUseFailure"):
        return None
    ti = ev.get("tool_input", {}) or {}
    if event_type == "PostToolUseFailure":
        return ti, str(ev.get("error") or "tool call failed")
    tr = ev.get("tool_response", {}) or {}
    text = bash_output_text(tr) if isinstance(tr, dict) else str(tr)
    return ti, text


def predicate(*, current_event: dict, history: list, pattern: Check,
              conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    if current_event.get("tool_name") != "Bash":
        return None
    prior = _most_recent_completed_bash_call(history)
    if prior is None:
        return None
    prior_input, prior_result_text = prior
    current_input = current_event.get("tool_input", {}) or {}
    if _canon_input(prior_input) != _canon_input(current_input):
        return None                          # not a retry of the SAME call -- silent
    if classify_failure(prior_result_text) is not True:
        return None                          # transient or uncertain -- never fire (the ship bar)
    return Finding(
        pattern_id=pattern.id,
        file="",
        line=0,
        level="error",  # Pre-tier is invariantly BLOCK; Check has no fire_level (test_pre_tier_block_invariant.py)
        message=("Identical retry of a Bash call that just failed deterministically -- retrying "
                 "the byte-identical command cannot change a deterministic error."),
        retry_hint=pattern.retry_hint,
    )


from makoto.registry import Check as _Check
RETRY_HINT = 'You retried the byte-identical failing Bash command with no intervening change, and the prior failure was deterministic (a syntax/import/permission/not-found error) -- retrying it unmodified cannot make progress. Change the command, fix the underlying cause, or take a different action.'
DESCRIPTION = "byte-identical Bash retry immediately following that SAME call's deterministic failure -- no intervening state change"

CHECK = _Check(id="event.identical_retry", applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('Bash',), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "history", "pattern"}), tests="TESTRUN_DELTA")
