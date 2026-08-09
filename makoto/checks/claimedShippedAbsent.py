from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import subprocess
from typing import Optional

from makoto.core.schema import Finding
from makoto.core.lexicons import (
    _SHIPPED_ACTION_CLAIM_RX, _SHIPPED_STATE_CLAIM_RX,
    _NEGATION_RX, _ADV_FORWARD_RX, _SENTENCE_SPLIT_RX,
)
from makoto.substrate.claims import _code_spans
from makoto.substrate.io import decode_history_row
from makoto.substrate._shared import _PUSH_BRANCH_RX
from makoto.core._shell import _command_pushes_git
import makoto.substrate.claim_graph as _claim_graph


class PushTipStatus(Enum):
    """The remote comparison's honest outcomes; NOT_EVALUABLE is outside a pass/fail verdict."""
    MATCH = "match"
    MISMATCH = "mismatch"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True)
class PushTipResult:
    status: PushTipStatus
    local_sha: str = ""
    remote_sha: str = ""
    detail: str = ""


def pushed_tip_matches_remote(text, cwd) -> PushTipResult:
    """Compare local HEAD to ``origin/<branch>`` with `ls-remote`.

    A missing branch, remote, network, or remote branch is NOT_EVALUABLE: no tool transcript is
    accepted as a proxy for this world fact. Git output and failures are deliberately treated as
    bounded evidence, so unusual ref output or a timeout also remains NOT_EVALUABLE.
    """
    if not text or not cwd:
        return PushTipResult(PushTipStatus.NOT_EVALUABLE, detail="missing claim text or cwd")
    match = _PUSH_BRANCH_RX.search(text)
    if not match:
        return PushTipResult(PushTipStatus.NOT_EVALUABLE, detail="push claim names no branch")
    branch = match.group(1).rstrip("`'\",:;.")
    if not branch:
        return PushTipResult(PushTipStatus.NOT_EVALUABLE, detail="empty branch")
    try:
        local = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3.0,
        )
        remote = subprocess.run(
            ["git", "-C", str(cwd), "ls-remote", "origin", branch],
            capture_output=True, text=True, timeout=3.0,
        )
    except Exception as exc:
        return PushTipResult(PushTipStatus.NOT_EVALUABLE, detail=f"git observation unavailable: {exc}")
    local_sha = local.stdout.strip()
    remote_fields = remote.stdout.strip().split()
    remote_sha = remote_fields[0] if remote_fields else ""
    if local.returncode != 0 or not local_sha:
        return PushTipResult(PushTipStatus.NOT_EVALUABLE, detail="local HEAD unavailable")
    if remote.returncode != 0 or not remote_sha:
        return PushTipResult(PushTipStatus.NOT_EVALUABLE, local_sha=local_sha,
                             detail="origin or branch unavailable")
    status = PushTipStatus.MATCH if local_sha == remote_sha else PushTipStatus.MISMATCH
    return PushTipResult(status, local_sha=local_sha, remote_sha=remote_sha)

# gate.claimed_shipped -- an immediate claim-vs-record integrity gate for completed REMOTE
# mutations. It owns "I pushed/merged/published/deployed/shipped/released X" and present-result
# claims such as "it's live now"; gate.completion continues to own local file-production claims.
#
# EVIDENCE is graph-bound, never existential over a flat history bag. A merge deed must name the
# same owner/repository/PR number and record ``merged: true``. A push claim is decided by comparing
# local HEAD with ``git ls-remote`` for the same repository, remote, and ref; a successful-looking
# push transcript is not a proxy for the remote world. Publish/deploy/release language without a
# provider-specific target observation remains NOT-EVALUABLE.
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
    """Legacy diagnostic for whether a flat history contains any remote mutation.

    The blocking gate does not use this broad boolean; graph resolvers require exact identity.
    """
    for row in history or ():
        ev = decode_history_row(row)
        if not isinstance(ev, dict) or ev.get("hook_event_name") != "PostToolUse":
            continue
        name = ev.get("tool_name", "")
        tool_input = ev.get("tool_input") or {}
        response = ev.get("tool_response")
        if name == "Bash":
            command = str(tool_input.get("command", "") or "") if isinstance(tool_input, dict) else ""
            if (_command_pushes_git(command)
                    and isinstance(response, dict)
                    and response.get("exitCode", response.get("exit")) == 0
                    and _response_succeeded(response)):
                return True
        elif name in _REMOTE_MUTATING_TOOL_NAMES and _response_succeeded(response):
            if name.endswith("merge_pull_request") and response.get("merged") is not True:
                continue
            return True
    return False


def claimed_shipped_gate(text, *, history=(), cwd=None, graph=None,
                         claim_ids=()) -> Optional[Finding]:
    """Reject a shipping claim without an exact repository/ref/PR support path."""
    if graph is None:
        graph, claim_ids = _claim_graph.build_ephemeral_graph(
            text, history=history, cwd=cwd, observe_push=True, run=subprocess.run,
        )
    claims = [
        graph.claims[claim_id] for claim_id in claim_ids
        if claim_id in graph.claims and graph.claims[claim_id].predicate.startswith("remote.")
    ]
    if not claims:
        return None
    for claim in claims:
        adjudication = graph.adjudicate(claim.node_id)
        if adjudication.verdict is _claim_graph.Verdict.CERTIFIED:
            continue
        if adjudication.verdict is _claim_graph.Verdict.CONTRADICTED:
            message = (
                f"Claim states {claim.predicate} for {claim.target_value}, but an exact-target "
                "world observation records the opposite state."
            )
        else:
            message = (
                f"Claim states {claim.predicate} for {claim.target_value}, but no successful deed "
                "or world observation names that same repository/ref/PR identity — a mutation "
                "of another target cannot certify it."
            )
        return Finding(
            pattern_id="gate.claimed_shipped", file="", line=0, level="error",
            message=message,
            retry_hint=("Actually push/merge the exact named target and obtain its observation, "
                        "or retract/rescope the shipping claim."),
        )
    return None


from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.claimed_shipped", applies_at="Stop", posture="BLOCK", may_block=True,
               run=lambda c: claimed_shipped_gate(
                   c.text, history=c.history_all_agents, cwd=c.cwd, graph=c.claim_graph,
                   claim_ids=c.current_claim_ids))
