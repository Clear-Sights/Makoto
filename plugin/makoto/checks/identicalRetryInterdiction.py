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

from typing import Optional

from makoto.kit import (bash_output_text, canon_input, classify_failure, decode_history_event,
                        failure_terminal_result, unwitnessed)
from makoto.vocab import Finding
from makoto.registry import Check

# The witness is the SINGLE MOST RECENT recorded act that exercised the same command -- a Bash
# call whose response was already read -- never a second, independent source.
SHAPE = "SWITCH"


def owes(ev):
    """The about-to-run CURRENT Bash call owes a witness that it is not a byte-identical retry
    of the immediately preceding call. `ev` is `("current", (prior_input, current_input))`; any
    other kind owes nothing. Embeds the canon_input equality test itself (like `canon_gate`'s own
    primitives), so a call whose input differs from the prior one never even raises the
    obligation -- there is nothing to interdict."""
    kind, payload = ev
    if kind != "current":
        return ()
    prior_input, current_input = payload
    if canon_input(prior_input) != canon_input(current_input):
        return ()
    return (canon_input(current_input),)


def pays(ev):
    """The PRIOR call's own recorded response is the only witness this predicate reads. `ev` is
    `("prior", prior_result_text)`; any other kind pays nothing. It pays the retry unconditionally
    whenever the prior call's classification is anything other than a confident deterministic
    failure (transient or uncertain both legitimize retrying) -- a confident deterministic failure
    pays nothing, leaving the identical retry owed."""
    kind, payload = ev
    if kind != "prior":
        return None
    if classify_failure(payload) is not True:
        return lambda _subject: True
    return None


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
    ti = ev.get("tool_input") or {}
    if event_type == "PostToolUseFailure":
        return ti, failure_terminal_result(ev)["error"]
    tr = ev.get("tool_response") or {}
    if isinstance(tr, dict):
        # A RECORDED zero exit is a call that SUCCEEDED: there is no failure to interdict,
        # whatever failure-shaped PHRASES its output happens to carry (e.g. grepping logs for
        # "No such file or directory" puts the marker in stdout of a passing call). Only an
        # explicitly recorded 0 short-circuits; an absent exit code still defers to
        # `classify_failure` over the output text, exactly as before.
        recorded_exit = tr.get("exitCode", tr.get("exit"))
        if recorded_exit == 0 and not isinstance(recorded_exit, bool):
            return None
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
    current_input = current_event.get("tool_input") or {}
    events = (("prior", prior_result_text), ("current", (prior_input, current_input)))
    for _ev, _subject in unwitnessed(events, owes=owes, pays=pays):
        return Finding(
            pattern_id=pattern.id,
            file="",
            line=0,
            level="error",  # Pre-tier is invariantly BLOCK; Check has no fire_level (test_pre_tier_block_invariant.py)
            message=("Identical retry of a Bash call that just failed deterministically -- retrying "
                     "the byte-identical command cannot change a deterministic error."),
            retry_hint=pattern.retry_hint,
        )
    return None


RETRY_HINT = 'You retried the byte-identical failing Bash command with no intervening change, and the prior failure was deterministic (a syntax/import/permission/not-found error) -- retrying it unmodified cannot make progress. Change the command, fix the underlying cause, or take a different action.'
DESCRIPTION = "byte-identical Bash retry immediately following that SAME call's deterministic failure -- no intervening state change"

CHECK = Check(id="event.identical_retry", applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('Bash',), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "history", "pattern"}), tests="TESTRUN_DELTA")
