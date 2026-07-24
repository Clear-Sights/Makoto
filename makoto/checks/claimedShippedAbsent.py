from __future__ import annotations
from typing import Optional

from makoto.core.schema import Finding
from makoto.core.lexicons import (
    _SHIPPED_ACTION_CLAIM_RX, _SHIPPED_STATE_CLAIM_RX, _REMOTE_GIT_PUSH_CMD_RX,
    _NEGATION_RX, _ADV_FORWARD_RX, _SENTENCE_SPLIT_RX,
)
from makoto.substrate.claims import _code_spans
from makoto.substrate.io import decode_history_row

# gate.claimed_shipped -- an immediate claim-vs-record integrity gate for completed REMOTE
# mutations. It owns "I pushed/merged/published/deployed/shipped/released X" and present-result
# claims such as "it's live now"; gate.completion continues to own local file-production claims.
#
# EVIDENCE is existential across the session's recorded PostToolUse history: (1) a successful,
# non-dry-run Bash `git push`, or (2) a successful call from the closed remote-mutation tool set
# below. Like gate.run_promised, this deliberately does not attempt semantic coreference between
# "it"/"#42" and a command's owner/repo/ref fields: guessing that mapping would create false
# blocks. Any successful remote mutation is enough grounding to fail open.
#
# CLOSED NON-BASH SET: GitHub's merge_pull_request and push_files are actual shipping actions.
# create_pull_request is intentionally excluded: opening a PR establishes review intent but does
# not substantiate "merged", "pushed", or "live". create_or_update_file is excluded for the same
# reason and remains closer to gate.completion. Both the bare MCP action names recorded by tests
# and Claude Code's fully-qualified `mcp__github__...` names are enumerated explicitly; no suffix
# or substring heuristic can silently admit a read-only tool.
_REMOTE_MUTATING_TOOL_NAMES = frozenset({
    "merge_pull_request",
    "push_files",
    "mcp__github__merge_pull_request",
    "mcp__github__push_files",
})


def _shipped_claim(text: str):
    """Return the first active completed-action or present-result shipping claim, else None.
    Quoted/fenced mentions and negated/forward-framed clauses are inert. Past passive forms do
    not enter either closed regex: the action regex requires first-person agency (or a boundary-
    anchored status-report verb), while the state regex permits present copulas only."""
    if not text:
        return None
    spans = _code_spans(text)
    matches = sorted(
        list(_SHIPPED_ACTION_CLAIM_RX.finditer(text))
        + list(_SHIPPED_STATE_CLAIM_RX.finditer(text)),
        key=lambda m: m.start(),
    )
    for m in matches:
        a = m.start()
        if any(s <= a < e for s, e in spans):
            continue
        clause = _SENTENCE_SPLIT_RX.split(text[max(0, a - 90):a])[-1] + m.group(0)
        if _NEGATION_RX.search(clause) or _ADV_FORWARD_RX.search(clause):
            continue
        return m
    return None


def _response_succeeded(response) -> bool:
    """Protocol-level success for a settled tool response. Missing/empty/errored responses fail
    closed as evidence (which can make the gate fire), because they do not record a genuinely
    successful mutation."""
    if not isinstance(response, dict) or not response:
        return False
    if response.get("interrupted") is True:
        return False
    exit_code = response.get("exitCode", response.get("exit"))
    if exit_code is not None and exit_code != 0:
        return False
    if any(response.get(k) not in (None, "", False) for k in ("error", "error_code", "is_error")):
        return False
    return True


def _successful_remote_mutation(history) -> bool:
    """True iff pooled history contains a completed, successful remote mutation."""
    for row in history or ():
        ev = decode_history_row(row)
        if not isinstance(ev, dict) or ev.get("hook_event_name") != "PostToolUse":
            continue
        name = ev.get("tool_name", "")
        tool_input = ev.get("tool_input") or {}
        response = ev.get("tool_response")
        if name == "Bash":
            command = str(tool_input.get("command", "") or "") if isinstance(tool_input, dict) else ""
            if (_REMOTE_GIT_PUSH_CMD_RX.search(command)
                    and isinstance(response, dict)
                    and response.get("exitCode", response.get("exit")) == 0
                    and _response_succeeded(response)):
                return True
        elif name in _REMOTE_MUTATING_TOOL_NAMES and _response_succeeded(response):
            if name.endswith("merge_pull_request") and response.get("merged") is not True:
                continue
            return True
    return False


def claimed_shipped_gate(text, *, history=()) -> Optional[Finding]:
    """Fire immediately when a completed remote-shipping claim has no successful mutation
    evidence anywhere in the session's pooled history."""
    claim = _shipped_claim(text)
    if claim is None or _successful_remote_mutation(history):
        return None
    return Finding(
        pattern_id="gate.claimed_shipped", file="", line=0, level="error",
        message=(f"Claim states a remote change was shipped "
                 f"(\"{claim.group(0).strip()}\") but no successful remote-mutating tool call "
                 "appears anywhere in this session's recorded history — the word must match "
                 "the world."),
        retry_hint=("Actually push/merge it with a successful recorded tool call, or "
                    "retract/rescope the shipping claim."),
    )


from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.claimed_shipped", applies_at="Stop", posture="BLOCK", may_block=True,
               run=lambda c: claimed_shipped_gate(c.text, history=c.history_all_agents))
