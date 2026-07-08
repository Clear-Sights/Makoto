"""makoto.checks.identicalRetryInterdiction -- D1 (docs/DEFERRED.md): PreToolUse interdiction of
a byte-identical Bash retry immediately following a DETERMINISTIC failure of the SAME call --
"kills the loop at length 1," the PROACTIVE twin of canon.recur (canonTimeoutRecur.py, which is
reactive at Stop, judging a run of >=2 consecutive identical failing calls after the fact). This
fires BEFORE the redundant call even runs.

Ship bar (two Fable consultations, docs/DEFERRED.md D1): BLOCK-tier only, and ONLY when
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

from makoto.checks._failureClassifier import classify_failure
from makoto.lib.io import bash_output_text
from makoto.schema import Finding, PreCheck


def _canon_input(ti: dict) -> str:
    try:
        return json.dumps(ti, sort_keys=True, default=str)
    except Exception:
        return repr(ti)


def _decode_row(row) -> Optional[dict]:
    """One history row -> its decoded hook payload dict, or None. Accepts both the live
    events-table tuple shape (id, ts, event_type, cwd, raw_payload_json) and a dict with a
    'payload' key (corpus/replay callers) -- the same row union makoto.lib.io.iter_tool_events
    decodes, kept local (not imported) so this predicate has no cross-module coupling at all."""
    if isinstance(row, (tuple, list)) and len(row) > 4:
        raw = row[4]
    elif hasattr(row, "get"):
        raw = row.get("payload")
    else:
        return None
    if not raw:
        return None
    try:
        ev = raw if isinstance(raw, dict) else json.loads(raw)
    except Exception:
        return None
    return ev if isinstance(ev, dict) else None


def _most_recent_completed_bash_call(history) -> Optional[tuple]:
    """(tool_input, result_text) of the SINGLE MOST RECENT history row, iff that row is a
    PostToolUse Bash call -- else None (a different tool, a Pre row, or nothing at all)."""
    rows = list(history or ())
    if not rows:
        return None
    ev = _decode_row(rows[-1])
    if ev is None or ev.get("hook_event_name") != "PostToolUse" or ev.get("tool_name") != "Bash":
        return None
    ti = ev.get("tool_input", {}) or {}
    tr = ev.get("tool_response", {}) or {}
    text = bash_output_text(tr) if isinstance(tr, dict) else str(tr)
    return ti, text


def predicate(*, current_event: dict, history: list, pattern: PreCheck,
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
        level=pattern.fire_level,
        message=("Identical retry of a Bash call that just failed deterministically -- retrying "
                 "the byte-identical command cannot change a deterministic error."),
        retry_hint=pattern.retry_hint,
    )


from makoto.checks._loader import Check as _Check
RETRY_HINT = 'You retried the byte-identical failing Bash command with no intervening change, and the prior failure was deterministic (a syntax/import/permission/not-found error) -- retrying it unmodified cannot make progress. Change the command, fix the underlying cause, or take a different action.'
DESCRIPTION = "byte-identical Bash retry immediately following that SAME call's deterministic failure -- no intervening state change"

CHECK = _Check(id="event.identical_retry", applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('Bash',), retry_hint=RETRY_HINT, description=DESCRIPTION)
