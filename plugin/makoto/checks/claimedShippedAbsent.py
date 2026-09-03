from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import json
import subprocess
from typing import Optional

from makoto.vocab import Finding
from makoto.vocab import (
    _SHIPPED_ACTION_CLAIM_RX, _SHIPPED_STATE_CLAIM_RX,
    _NEGATION_RX, _ADV_FORWARD_RX, _SENTENCE_SPLIT_RX,
)
from makoto.substrate.claims import _code_spans
from makoto.kit import decode_history_row
from makoto.kit import extract_pushed_branch
from makoto.core._shell import _command_pushes_git


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
    branch: str = ""


def pushed_tip_matches_remote(text, cwd) -> PushTipResult:
    """Compare the claimed branch's LOCAL tip (``refs/heads/<branch>``) to ``origin``'s with
    `ls-remote`.

    A missing remote, network, or remote branch is NOT_EVALUABLE: no tool transcript is
    accepted as a proxy for this world fact. Git output and failures are deliberately treated as
    bounded evidence, so unusual ref output (including MORE than one answering ref line) or a
    timeout also remains NOT_EVALUABLE. A claim naming no branch falls back to the checked-out
    branch via `git symbolic-ref --short HEAD` — the same fallback `kit.pushed_ref_matches_world`
    uses — so a bare "I pushed it" is still evaluable. The LOCAL side is the branch ref, never
    bare HEAD: a true push to a branch that is not currently checked out must not read as a
    mismatch, and the compared branch is carried in the result so a DENY can name it.
    """
    if not text or not cwd:
        return PushTipResult(PushTipStatus.NOT_EVALUABLE, detail="missing claim text or cwd")
    # Pushed-branch extraction: kit.extract_pushed_branch (dedup: was a byte-identical
    # regex-search + rstrip pair with kit.pushed_ref_matches_world's own call site).
    branch = extract_pushed_branch(text)
    try:
        if branch is None:
            head = subprocess.run(
                ["git", "-C", str(cwd), "symbolic-ref", "--quiet", "--short", "HEAD"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3.0,
            )
            branch = head.stdout.strip() if head.returncode == 0 else ""
            if not branch:
                return PushTipResult(PushTipStatus.NOT_EVALUABLE,
                                     detail="push claim names no branch and HEAD is not on one")
        if not branch:
            return PushTipResult(PushTipStatus.NOT_EVALUABLE, detail="empty branch")
        local = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--verify", f"refs/heads/{branch}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3.0,
        )
        remote = subprocess.run(
            ["git", "-C", str(cwd), "ls-remote", "origin", f"refs/heads/{branch}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3.0,
        )
    except Exception as exc:
        return PushTipResult(PushTipStatus.NOT_EVALUABLE, detail=f"git observation unavailable: {exc}")
    local_sha = local.stdout.strip()
    remote_lines = [ln for ln in remote.stdout.splitlines() if ln.strip()]
    remote_fields = remote_lines[0].split() if remote_lines else []
    remote_sha = remote_fields[0] if remote_fields else ""
    if local.returncode != 0 or not local_sha:
        return PushTipResult(PushTipStatus.NOT_EVALUABLE, branch=branch,
                             detail=f"local refs/heads/{branch} unavailable")
    if remote.returncode != 0 or not remote_sha:
        return PushTipResult(PushTipStatus.NOT_EVALUABLE, local_sha=local_sha, branch=branch,
                             detail="origin or branch unavailable")
    if len(remote_lines) > 1:
        return PushTipResult(PushTipStatus.NOT_EVALUABLE, local_sha=local_sha, branch=branch,
                             detail="ambiguous ls-remote output (multiple answering refs)")
    status = PushTipStatus.MATCH if local_sha == remote_sha else PushTipStatus.MISMATCH
    return PushTipResult(status, local_sha=local_sha, remote_sha=remote_sha, branch=branch)

# gate.claimed_shipped -- an immediate claim-vs-record integrity gate for completed REMOTE
# mutations. It owns "I pushed/merged/published/deployed/shipped/released X" and present-result
# claims such as "it's live now"; gate.completion continues to own local file-production claims.
#
# EVIDENCE is existential across the session's recorded PostToolUse history for merge/publish-like
# claims. A push claim is different: it is decided by comparing the local `refs/heads/<branch>`
# tip with `git ls-remote origin refs/heads/<branch>`, so a successful-looking push transcript is
# never accepted as a proxy while the world is observable. Like gate.run_promised, the non-push evidence deliberately does not attempt semantic
# coreference between "it"/"#42" and a command's owner/repo/ref fields.
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


def _shipped_claim(text: str, *, start: int = 0):
    """The first active completed-action or present-result shipping claim starting at or after
    offset `start`, else None. The gate walks EVERY claim by advancing `start`, so an
    unevaluable first claim can never shadow a checkable later one. Quoted/fenced mentions and
    negated/forward-framed clauses are inert. Past passive forms do not enter either closed
    regex: the action regex requires first-person agency (or a boundary-anchored status-report
    verb), while the state regex permits present copulas only."""
    if not text:
        return None
    matches = sorted(
        [*_SHIPPED_ACTION_CLAIM_RX.finditer(text), *_SHIPPED_STATE_CLAIM_RX.finditer(text)],
        key=lambda m: m.start(),
    )
    matches = [m for m in matches if m.start() >= start]
    if not matches:
        return None                     # no candidate claim -> skip the fence/backtick span scan
    spans = _code_spans(text)
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
    successful mutation. A response delivered as a JSON *string* (a live MCP shape) is parsed
    first, so real evidence is not rejected on shape alone; the exit-code fallback treats an
    explicit `exitCode: None` like an absent key, so `{"exitCode": None, "exit": 3}` cannot
    read as settled success."""
    if isinstance(response, str):
        try:
            parsed = json.loads(response)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            response = parsed
    if not isinstance(response, dict) or not response:
        return False
    if response.get("interrupted") is True:
        return False
    exit_code = response.get("exitCode")
    if exit_code is None:
        exit_code = response.get("exit")
    if exit_code is not None and exit_code != 0:
        return False
    if any(response.get(k) not in (None, "", False) for k in ("error", "error_code", "is_error")):
        return False
    return True


def _successful_remote_mutation(history) -> Optional[bool]:
    """Three-valued pooled-history evidence for a completed remote mutation.

      True  — a settled, successful remote mutation is recorded; the claim is discharged.
      False — the gate is GROUNDED and the evidence is negative: either a real remote-mutation
              ATTEMPT is recorded and none of them settled successfully, or nothing
              remote-shaped happened at all in a window that also contains no unclassifiable
              Bash call. This is the firing case.
      None  — NOT-EVALUABLE, and therefore SILENT. The gate could not decide, and a miss must
              never be spent as a positive assertion of absence.

    WHY None EXISTS (the sibling defect, gate.claimed_running / `_latest_process_call_failed`):
    this module's remote-mutation vocabulary is CLOSED — `_REMOTE_MUTATING_TOOL_NAMES` (four
    exact MCP names) plus `_command_pushes_git` (an argv parse that recognizes `git push`, and
    nothing else). This estate ships by many other shapes: `gh pr merge`, `gh release create`,
    `npm publish`, `docker push`, `flyctl deploy`, `./deploy.sh`, `scp`, `rsync`. Every one of
    them is a vocabulary MISS. Returning False there told an agent that had genuinely shipped
    that "no recorded mutation evidence backs it" — a false block in the expensive direction,
    the exact shape just repaired in gate.claimed_running.

    So a recorded Bash terminal whose command is NOT a recognized push makes the window
    undecidable: any Bash command could be a shipping action this net cannot read. Likewise an
    UNDECODABLE row — the dropped row could be the very mutation the claim cites.

    The doubt flags apply ONLY when nothing matched. Once a real attempt IS recorded the gate is
    grounded and an unrelated `ls` in the same window cannot buy the claim silence.

    NOT FIXED BY WIDENING THE NET: a longer closed list is exactly as monotone as a short one,
    and the next unlisted shipping command would false-block identically.

    RECALL COST, stated rather than hidden: an agent that runs ANY Bash command at all and then
    claims a non-push shipping action it never performed is no longer blocked by this arm. The
    teeth that remain are (a) an empty / Bash-free window, (b) a recorded attempt that failed,
    and (c) for push claims specifically, `pushed_tip_matches_remote`'s MISMATCH against the
    real remote, which reads the world and not the vocabulary.
    """
    saw_undecodable = False
    saw_unreadable_bash = False
    saw_attempt = False

    def _as_dict(response):
        # The live harness can deliver an MCP result as a JSON string; parse it so real
        # evidence is not rejected on shape alone.
        if isinstance(response, str):
            try:
                parsed = json.loads(response)
            except ValueError:
                return response
            if isinstance(parsed, dict):
                return parsed
        return response

    def _merged_true(response) -> bool:
        # `merged: true` across the shapes the live harness delivers: a bare dict, or Claude
        # Code's MCP envelope {"content": [{"type": "text", "text": "{...json...}"}]} — a
        # genuinely merged PR must not be DENIED because the truth arrived wrapped.
        if not isinstance(response, dict):
            return False
        if response.get("merged") is True:
            return True
        content = response.get("content")
        if isinstance(content, list):
            for item in content:
                if not (isinstance(item, dict) and item.get("type") == "text"):
                    continue
                try:
                    payload = json.loads(item.get("text") or "")
                except ValueError:
                    continue
                if isinstance(payload, dict) and payload.get("merged") is True:
                    return True
        return False

    for row in history or ():
        ev = decode_history_row(row)
        if not isinstance(ev, dict):
            saw_undecodable = True
            continue
        if ev.get("hook_event_name") != "PostToolUse":
            continue
        name = ev.get("tool_name", "")
        response = _as_dict(ev.get("tool_response"))
        if name == "Bash":
            tool_input = ev.get("tool_input")
            command = str(tool_input.get("command", "") or "") if isinstance(tool_input, dict) else ""
            # Stricter than _response_succeeded alone: a push terminal must carry an EXPLICIT zero
            # exit code, not merely the absence of an error field. _response_succeeded runs first
            # because it subsumes the dict guard the .get() pair below needs; the exitCode ->
            # exit fallback tolerates an explicit None like _response_succeeded's own.
            exit_code = response.get("exitCode") if isinstance(response, dict) else None
            if exit_code is None and isinstance(response, dict):
                exit_code = response.get("exit")
            if not _command_pushes_git(command):
                # A Bash terminal this net cannot classify. `gh pr merge`, `npm publish`,
                # `docker push`, `./deploy.sh` all land here — so does `ls`. The check cannot
                # tell them apart, which is precisely why the window stops being decidable.
                saw_unreadable_bash = True
                continue
            saw_attempt = True
            if _response_succeeded(response) and exit_code == 0:
                return True
        elif name in _REMOTE_MUTATING_TOOL_NAMES:
            saw_attempt = True
            if _response_succeeded(response):
                if name.endswith("merge_pull_request") and not _merged_true(response):
                    continue
                return True
    if saw_attempt:
        return False            # grounded: a real attempt is recorded and none of them succeeded
    if saw_undecodable or saw_unreadable_bash:
        return None             # NOT-EVALUABLE: a vocabulary miss is silent, never an assertion
    return False


def claimed_shipped_gate(text, *, history=(), cwd=None) -> Optional[Finding]:
    """Fire an unbacked shipping claim; pushes use the remote tip, not a tool signature.

    EVERY active claim in the message is examined in order — the first that fails its check
    fires — so an unevaluable push claim can no longer shadow a later, fully checkable claim
    (previously only the FIRST claim was ever looked at). Push-claim routing, matching the
    pinned batteries (tests/test_delegated_world_evidence.py,
    tests/test_gate_claimed_shipped_live_battery.py, tests/test_makaudit_regressions.py):

      * MATCH upholds the claim; MISMATCH fires a push-is-false Finding naming the branch.
      * NOT_EVALUABLE with a cwd PRESENT stays silent — with a worktree at hand, an
        unobservable remote is deliberate fail-open; neither a transcript nor a history gap
        is remote evidence.
      * With NO cwd at all, nothing world-side is consultable, so the claim falls back to the
        recorded-mutation-evidence route: a settled successful mutation discharges it, a
        recorded ATTEMPT that never settled successfully (a failed `git push`, a dangling
        PreToolUse mutation row) FIRES — absence is checked, never read as green with nothing
        checked at all — while a history with no attempted remote mutation whatsoever (e.g.
        only an `echo 'git push ...'`) remains outside a verdict.

    WHAT THIS GATE CANNOT DECIDE (stated, not hidden — it reads a raw Bash command string and
    has no typed "this call shipped something" field to read instead; the Bash tool envelope
    carries only `tool_input.command`):

      * WHICH command shipped. `_command_pushes_git` parses argv and recognizes `git push`
        alone. Every other shipping shape (`gh pr merge`, `npm publish`, `docker push`,
        `./deploy.sh`) is unreadable, so `_successful_remote_mutation` answers None and this
        gate stays SILENT rather than asserting absence.
      * WHETHER a claim's object is the thing a recorded command touched. No coreference
        between "it" / "#42" and a command's owner/repo/ref is attempted, deliberately.
      * WHETHER a non-push remote mutation actually reached the world. Only the push arm
        consults the world (`ls-remote`); merge/publish/deploy claims rest on the transcript.
    """

    def _attempted_remote_mutation(rows) -> bool:
        # An ATTEMPT at a remote mutation, settled or not: any phase of a real push command or
        # of a closed-set remote-mutating tool. `echo 'git push'` is not an attempt
        # (_command_pushes_git parses argv, not substrings); neither is a --dry-run push.
        for row in rows or ():
            ev = decode_history_row(row)
            if not isinstance(ev, dict):
                continue
            name = ev.get("tool_name", "")
            if name in _REMOTE_MUTATING_TOOL_NAMES:
                return True
            if name == "Bash":
                tool_input = ev.get("tool_input")
                command = (str(tool_input.get("command", "") or "")
                           if isinstance(tool_input, dict) else "")
                if _command_pushes_git(command):
                    return True
        return False

    pos = 0
    while True:
        claim = _shipped_claim(text, start=pos)
        if claim is None:
            return None
        pos = claim.end()
        push_claim = "pushed" in claim.group(0).lower()
        if push_claim:
            tip = pushed_tip_matches_remote(text, cwd)
            if tip.status is PushTipStatus.MISMATCH:
                return Finding(
                    pattern_id="gate.claimed_shipped", file="", line=0, level="error",
                    message=(f"Push claim (\"{claim.group(0).strip()}\") is false: local "
                             f"refs/heads/{tip.branch} is {tip.local_sha}, but "
                             f"origin/{tip.branch} has {tip.remote_sha}."),
                    retry_hint="Push the local branch, or retract/rescope the push claim.",
                )
            if tip.status is PushTipStatus.MATCH or cwd:
                continue        # upheld, or world present but unobservable (fail-open)
            if not _attempted_remote_mutation(history):
                continue        # no cwd AND no recorded attempt: outside a verdict
        # Three-valued: True discharges the claim, None is NOT-EVALUABLE and stays silent.
        # ONLY an explicit False — a grounded negative — reaches the Finding below, so a
        # vocabulary miss can never be spent as a positive assertion that nothing shipped.
        if _successful_remote_mutation(history) is not False:
            continue
        return Finding(
            pattern_id="gate.claimed_shipped", file="", line=0, level="error",
            message=(f"Claim states a remote change was shipped "
                     f"(\"{claim.group(0).strip()}\") but no recorded mutation evidence "
                     "backs it — the word must match the world."),
            retry_hint=("Actually push/merge it so the world records the mutation, or "
                        "retract/rescope the shipping claim."),
        )


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.claimed_shipped", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="CLAIM_VS_HISTORY",
               eats=frozenset({"text", "history_all_agents", "cwd"}),
               run=lambda c: claimed_shipped_gate(
                   c.text, history=c.history_all_agents, cwd=c.cwd))
