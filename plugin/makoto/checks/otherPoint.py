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
from makoto.kit import unwitnessed
from makoto.core._shell import _command_pushes_git

# gate.claimed_shipped's SHAPE (see plugin/makoto/kit.py's `unwitnessed`) is genuinely mixed: a
# push claim's witness is OTHER_POINT (a second, independent reading of the same branch tip via
# `git ls-remote`), while every other shipped/merged/published/deployed/released claim's witness
# is SWITCH (a recorded act -- a settled remote-mutating tool call -- whose response was read).
# Declared as the dominant shape (SWITCH covers non-push claims outright, and is also the
# fallback a push claim reaches once its own tip comparison is NOT_EVALUABLE); see the return
# report's SPLIT annotation for the other half.
shipped_SHAPE = "SWITCH"


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
    branch via `git symbolic-ref --short HEAD` -- so a bare "I pushed it" is still evaluable.
    The LOCAL side is the branch ref, never bare HEAD: a true push to a branch that is not
    currently checked out must not read as a mismatch, and the compared branch is carried in the
    result so a DENY can name it.
    """
    if not text or not cwd:
        return PushTipResult(PushTipStatus.NOT_EVALUABLE, detail="missing claim text or cwd")
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
# never accepted as a proxy while the world is observable. Like gate.claimed_running, the non-push evidence deliberately does not attempt semantic
# coreference between "it"/"#42" and a command's owner/repo/ref fields.
#
# CLOSED NON-BASH SET: GitHub's merge_pull_request, push_files AND create_or_update_file are
# actual shipping actions -- each one lands a real commit on a real ref via the REST Contents/
# Pulls API the moment it returns success, with no local git object touched at all.
# create_or_update_file belongs here, not with gate.completion: that gate reads Write/Edit rows
# against the LOCAL filesystem, and this tool never touches one -- it commits straight to the
# target branch on origin. create_pull_request remains the one deliberate exclusion: opening a PR
# establishes review intent but does not substantiate "merged", "pushed", or "live" -- no ref
# moves and nothing merges until a separate call succeeds. Both the bare MCP action names and
# Claude Code's fully-qualified `mcp__github__...` names are enumerated explicitly; no suffix or
# substring heuristic can silently admit a read-only tool.
_REMOTE_MUTATING_TOOL_NAMES = frozenset({
    "merge_pull_request",
    "push_files",
    "create_or_update_file",
    "mcp__github__merge_pull_request",
    "mcp__github__push_files",
    "mcp__github__create_or_update_file",
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


def _first_json_object_in_content_blocks(content) -> Optional[dict]:
    """The first JSON *object* decoded out of a list of MCP content blocks, else None.

    Claude Code's PostToolUse `tool_response` for a settled MCP tool call is delivered as
    `toolUseResult` VERBATIM, not normalized to a typed dict the way a Bash terminal's
    stdout/stderr/exitCode envelope is. For every MCP call this module has direct evidence for —
    a real, successful `mcp__github__merge_pull_request` recorded mid-session, and
    `mcp__Claude_Code_Remote__add_repo` beside it — that shape is a BARE LIST of content blocks,
    `[{"type": "text", "text": "<json-or-plain-text>"}]`, with no enclosing `{"content": [...]}`
    dict. This one function is the single unwrap both `_merged_true` (called on an
    already-dict-wrapped content list) and `_as_dict` (called on this bare-list top-level shape)
    read from, so the two entry points can't drift into re-parsing the same wire shape two
    different ways. Text that is not valid JSON — a plain error string, prose — is left alone:
    inventing a dict out of it would let an unstructured failure message read as evidence of a
    settled mutation, exactly backwards for a gate whose whole job is not doing that."""
    if not isinstance(content, list):
        return None
    for item in content:
        if not (isinstance(item, dict) and item.get("type") == "text"):
            continue
        try:
            payload = json.loads(item.get("text") or "")
        except ValueError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _successful_remote_mutation(history) -> Optional[bool]:
    """Three-valued pooled-history evidence for a completed remote mutation.

      True  — a settled, successful remote mutation is recorded; the claim is discharged.
      False — the gate is GROUNDED and the evidence is negative: either a real remote-mutation
              ATTEMPT is recorded and none of them settled successfully, or nothing
              remote-shaped happened at all in a window that also contains no unclassifiable
              Bash call. This is the firing case.
      None  — NOT-EVALUABLE, and therefore SILENT. The gate could not decide, and a miss must
              never be spent as a positive assertion of absence.

    This module's remote-mutation vocabulary is CLOSED — `_REMOTE_MUTATING_TOOL_NAMES` (six
    exact MCP names) plus `_command_pushes_git` (an argv parse that recognizes `git push`, and
    nothing else). Real shipping happens by many other shapes too: `gh pr merge`, `gh release
    create`, `npm publish`, `docker push`, `flyctl deploy`, `./deploy.sh`, `scp`, `rsync`. Each
    is a vocabulary MISS, so a recorded Bash terminal whose command is NOT a recognized push
    makes the window undecidable rather than negative — any Bash command could be a shipping
    action this net cannot read. Likewise an UNDECODABLE row — the dropped row could be the very
    mutation the claim cites.

    Settled-success evidence must also survive the WIRE SHAPE: a settled MCP call's
    `tool_response` (Claude Code's `toolUseResult`, verbatim) can arrive as a BARE LIST of
    content blocks — `[{"type": "text", "text": "<json>"}]` — rather than a dict, which
    `_response_succeeded`/`_merged_true` both require. `_as_dict` below decodes that list shape
    the same way `_merged_true` decodes a dict-wrapped one, the same JSON-in-text-block unwrap
    applied at two entry points, so a genuinely successful merge/push/commit through the GitHub
    MCP tools is never read as an unsettled attempt merely because the truth arrived wrapped.

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
        # The live harness can deliver a settled MCP result as a JSON STRING, or as a BARE LIST
        # of content blocks (`[{"type": "text", "text": "<json-or-plain>"}]`) with no enclosing
        # dict at all. Decode either into the dict `_response_succeeded`/`_merged_true` need; a
        # content block whose text is not JSON (a plain error string, prose) is left unparsed on
        # purpose — fabricating a dict out of prose would let a vague failure message read as
        # shipping evidence, the opposite of this gate's job.
        if isinstance(response, str):
            try:
                parsed = json.loads(response)
            except ValueError:
                return response
            if isinstance(parsed, dict):
                return parsed
            response = parsed              # a JSON list/scalar embedded in a string
        if isinstance(response, list):
            payload = _first_json_object_in_content_blocks(response)
            if payload is not None:
                return payload
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
    fires — so an unevaluable push claim can never shadow a later, fully checkable claim. See
    `_claim_grounded` for the push-vs-non-push routing this reduces to.
    """
    def _attempted_remote_mutation(rows) -> bool:
        # An ATTEMPT at a remote mutation, settled or not: any phase of a real push command or
        # of a closed-set remote-mutating tool. `echo 'git push'` is not an attempt
        # (`_command_pushes_git` parses argv, not substrings); neither is a --dry-run push.
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

    def owes(t):
        # Every active shipped/merged/published/deployed/released claim in `t`, in order --
        # cheap and pure; the witness for each (the push tip's OTHER_POINT world-read, or the
        # SWITCH-shaped recorded-mutation evidence) lives in `paid`, below, so a claim after the
        # first unwitnessed one is never even evaluated.
        claims = []
        pos = 0
        while True:
            claim = _shipped_claim(t, start=pos)
            if claim is None:
                return claims
            pos = claim.end()
            claims.append(claim)

    def pays(_t):
        return None

    def _claim_grounded(claim) -> bool:
        # True (paid/silent) unless the claim is a positive, checkable contradiction. Push-claim
        # routing, matching the pinned batteries (tests/test_delegated_world_evidence.py,
        # tests/test_gate_claimed_shipped_live_battery.py, tests/test_makaudit_regressions.py):
        #
        #   * MATCH upholds the claim; MISMATCH is ungrounded (fires a push-is-false Finding
        #     naming the branch).
        #   * NOT_EVALUABLE with a cwd PRESENT is grounded (silent) — with a worktree at hand,
        #     an unobservable remote is deliberate fail-open; neither a transcript nor a history
        #     gap is remote evidence.
        #   * With NO cwd at all, nothing world-side is consultable, so the claim falls back to
        #     the recorded-mutation-evidence route below: a settled successful mutation
        #     discharges it, a recorded ATTEMPT that never settled successfully (a failed
        #     `git push`, a dangling PreToolUse mutation row) is ungrounded — absence is
        #     checked, never read as green with nothing checked at all — while a history with no
        #     attempted remote mutation whatsoever (e.g. only an `echo 'git push ...'`) remains
        #     outside a verdict (grounded/silent).
        #
        # WHAT THIS CANNOT DECIDE (stated, not hidden — it reads a raw Bash command string and
        # has no typed "this call shipped something" field to read instead; the Bash tool
        # envelope carries only `tool_input.command`):
        #
        #   * WHICH command shipped. `_command_pushes_git` parses argv and recognizes
        #     `git push` alone. Every other shipping shape (`gh pr merge`, `npm publish`,
        #     `docker push`, `./deploy.sh`) is unreadable, so `_successful_remote_mutation`
        #     answers None and this stays grounded (silent) rather than asserting absence.
        #   * WHETHER a claim's object is the thing a recorded command touched. No coreference
        #     between "it" / "#42" and a command's owner/repo/ref is attempted, deliberately.
        #   * WHETHER a non-push remote mutation actually reached the world. Only the push arm
        #     consults the world (`ls-remote`); merge/publish/deploy claims rest on the
        #     transcript.
        if "pushed" in claim.group(0).lower():
            tip = pushed_tip_matches_remote(text, cwd)
            if tip.status is PushTipStatus.MISMATCH:
                return False
            if tip.status is PushTipStatus.MATCH or cwd:
                return True         # upheld, or world present but unobservable (fail-open)
            if not _attempted_remote_mutation(history):
                return True         # no cwd AND no recorded attempt: outside a verdict
        # Three-valued: True discharges the claim, None is NOT-EVALUABLE and stays silent
        # (grounded). ONLY an explicit False — a grounded negative — is ungrounded here, so a
        # vocabulary miss can never be spent as a positive assertion that nothing shipped.
        return _successful_remote_mutation(history) is not False

    for _ev, claim in unwitnessed((text,), owes=owes, pays=pays, paid=(_claim_grounded,)):
        if "pushed" in claim.group(0).lower():
            tip = pushed_tip_matches_remote(text, cwd)
            if tip.status is PushTipStatus.MISMATCH:
                return Finding(
                    pattern_id="gate.claimed_shipped", file="", line=0, level="error",
                    message=(f"Push claim (\"{claim.group(0).strip()}\") is false: local "
                             f"refs/heads/{tip.branch} is {tip.local_sha}, but "
                             f"origin/{tip.branch} has {tip.remote_sha}."),
                    retry_hint="Push the local branch, or retract/rescope the push claim.",
                )
        return Finding(
            pattern_id="gate.claimed_shipped", file="", line=0, level="error",
            message=(f"Claim states a remote change was shipped "
                     f"(\"{claim.group(0).strip()}\") but no recorded mutation evidence "
                     "backs it — the word must match the world."),
            retry_hint=("Actually push/merge it so the world records the mutation, or "
                        "retract/rescope the shipping claim."),
        )
    return None


from makoto.registry import Check as _Check
shipped_CHECK = _Check(id="gate.claimed_shipped", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="OTHER_POINT",
               eats=frozenset({"text", "history_all_agents", "cwd"}),
               run=lambda c: claimed_shipped_gate(
                   c.text, history=c.history_all_agents, cwd=c.cwd))

import os
import re
from makoto.checks import detect_locations, normalize_path
from makoto.vocab import (
    _PRODUCE_VERB_RX, _BE_AUX_RX, _CLAUSE_BREAK_RX, _FORWARD_FRAME_RX, _NEG_FRAME_RX,
)
from makoto.kit import (_BIND_BEFORE, CARRIAGE_FAULT, DISCHARGE_EATS, _discharge_kwargs,
                        _discharged, resolve_in_worktree, unwitnessed)

# gate.completion's SHAPE (see plugin/makoto/kit.py's `unwitnessed`): OTHER_POINT -- the witness
# is a second reading of the same subject (the results ledger, or the filesystem itself).
completion_SHAPE = "OTHER_POINT"


# A subordinate-clause marker or a READ/relational FRAME appearing in the verb->path gap means an
# intervening noun phrase + clause separates the produce verb from the path: the verb governs a
# DIFFERENT direct object ("updated the logic so … config.yaml", "wrote the handler to read from
# settings.json"), and the path is an inert reference (a read source, a constraint), not the
# authored object. A genuine production claim ("I wrote config.yaml", "created `handler.py`",
# "added X to `src/auth.py`") has either an essentially-empty gap (whitespace / article / quote /
# adjective) or a production-DESTINATION preposition before the path.
#
# Deliberately NOT in this set: a bare `to` / `from` / `that`. Those are the canonical
# production-target prepositions — "added the handler TO src/auth.py", "wrote the migration TO
# 0007.sql" are real production claims, not references. Their referencing uses are caught by the
# fuller frame instead: `read(s) from` (the read FP), `so` / `matches` / `requires` (the
# subordinate-clause FP). Including bare `to`/`from` over-narrowed and silenced live TPs
# (tests/test_gates.py + tests/test_substrate_teeth.py pin the TPs).
# How far back before the produce verb a forward/negation frame is looked for, to disarm the
# claim ("will add `X`", "didn't add `X`"). Deliberately narrower than the verb->path bind
# (_BIND_BEFORE) so a stray "not"/"next" far upstream cannot silence a live claim, AND trimmed
# at the last clause break inside the window, so a negation in the PRECEDING sentence ("Two
# tests still do not pass. I created X") cannot disarm a live current-clause claim either.
_FRAME_NEAR = 40
_PRODUCE_OBJ_SEP_RX = re.compile(
    r"\b(?:so|against|match(?:es|ing)?|reads?\s+from|requires?|"
    r"according\s+to|based\s+on|conform(?:s|ing)?\s+to)\b", re.I)
_PASSIVE_PREFIX_RX = re.compile(
    r"\b(?:was|were|is|are|been|being|be|am)(?:\s+[\w-]+){0,2}\s*$", re.IGNORECASE)


def _production_claim_locations(text):
    """Yield located paths that are direct objects of ACTIVE first-person production claims.

    Required structure (the 'make it clearer' fix for the measured FP): a produce verb sits
    BEFORE the path, in the SAME clause, in active voice — "I created `X`", "Wrote `X`". A
    path is INERT when no produce verb governs it (a heading, a reference, a deliverable
    list), when the verb is passive/copular ("`X` was written", "it's wired"), when a clause
    break separates them ("deletions landed; … the `X`"), when a negation stands in the
    verb->path gap ("updated the docs, though I never created `X`" — the later, negated verb
    is the one governing the path, so the earlier verb must not hijack it), or in a
    forward/negated frame ("will add `X`", "didn't add `X`"). This is the verifiable core: a
    claim the assistant itself produced this specific file."""
    if not text:
        return
    for loc, a, b in detect_locations(text):
        before = text[max(0, a - _BIND_BEFORE):a]
        for vm in _PRODUCE_VERB_RX.finditer(before):
            pre = before[:vm.start()]
            if _BE_AUX_RX.search(pre) or _PASSIVE_PREFIX_RX.search(pre):
                continue                              # passive/copular -> not a self-production claim
            between = before[vm.end():]
            if _CLAUSE_BREAK_RX.search(between):
                continue                              # verb governs a different clause's noun
            if _PRODUCE_OBJ_SEP_RX.search(between):
                continue                              # subordinator/read-frame separates verb and
                                                      # path -> path is a referenced source, not the
                                                      # verb's direct object (the measured FP)
            if _NEG_FRAME_RX.search(between):
                continue                              # "updated ..., though I never created X" ->
                                                      # the negated later verb governs the path;
                                                      # the claim text explicitly disowns it
            near = pre[-_FRAME_NEAR:]
            trailing_break = None
            for trailing_break in _CLAUSE_BREAK_RX.finditer(near):
                pass                                  # keep the LAST clause break in the window
            if trailing_break is not None:
                # Trim the frame window at the last clause break: a negation or forward frame
                # in the PREVIOUS sentence ("Two tests still do not pass. I created X") must
                # not disarm a live, current-clause claim — absence would read as green.
                near = near[trailing_break.end():]
            if _FORWARD_FRAME_RX.search(near):
                continue                              # "will add X" -> a plan, not a claim
            if _NEG_FRAME_RX.search(near):
                continue                              # "didn't add X" -> admission (2.8), not a false claim
            yield loc
            break


def completion_gate(
    text, *, touched_keys, fs_exists=None, empty_keys=None, fs_size=None, cwd=None,
) -> Optional[Finding]:
    """Fire iff the assistant CLAIMS it produced a specific file (a produce verb governs a
    located path, non-forward, non-negated) but that file is neither in the results ledger
    nor on disk — a verifiable contradiction between the word and the world.

    What is INERT (the measured-FP fix, by being clearer not by firing less):
      - a bare done-word with no location              (nothing to verify)
      - a path with no governing produce verb           (a heading, a reference, a code
                                                          listing, a subagent's deliverable)
      - a non-path token (version/SHA/duration/task-id) (the location regex no longer matches it)
      - a forward/negated frame                          ("will add X", "didn't add X")
    A produced-claim that IS touched, or that the filesystem confirms, is silent (fail-open).
    Only an unbacked production claim bites.
    """
    def owes(t):
        # Every located claim in `t` -- cheap and pure; the witness (a second reading of that
        # same location, in the ledger or on disk) lives in `paid`, below, so a location after
        # the first unwitnessed one is never even checked.
        return list(_production_claim_locations(t))

    def pays(_t):
        return None

    def _location_grounded(loc) -> bool:
        # True (paid/silent) iff a second reading of `loc` backs the claim: the results ledger,
        # the caller-supplied filesystem read, or -- widened to the worktree -- the real
        # filesystem there. `CARRIAGE_FAULT` (the worktree could not be resolved) also pays: an
        # unreadable worktree must never widen what is blocked.
        if _discharged(loc, touched_keys, fs_exists, empty_keys=empty_keys, fs_size=fs_size):
            return True                               # verified (ledger) or fail-open (filesystem)
        worktree_path = resolve_in_worktree(loc, cwd)
        if worktree_path is CARRIAGE_FAULT:
            return True
        if worktree_path:
            # Preserve _discharged's content-depth law for this widened path: a zero-byte
            # non-conventional artifact still does not substantiate a production claim.
            return _discharged(
                loc, (), fs_exists=lambda _p: True,
                fs_size=lambda _p: os.path.getsize(worktree_path),
            )
        return False

    for _ev, loc in unwitnessed(
            (text,), owes=owes, pays=pays, paid=(_location_grounded,)):
        loc_n = normalize_path(loc)
        return Finding(
            pattern_id="gate.completion",
            file=loc_n,
            line=0,
            level="error",
            message=(f"Claim states {loc_n} was produced, but it is neither in the results "
                     f"ledger nor on disk — the word must match the world."),
            retry_hint="Produce/touch the cited location, or retract with a checked reason.",
        )
    return None


completion_CHECK = _Check(id="gate.completion", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="OTHER_POINT",
               eats=DISCHARGE_EATS | frozenset({"text", "cwd"}),
               run=lambda c: completion_gate(c.text, cwd=c.cwd, **_discharge_kwargs(c)))

from makoto.checks import normalize_path
from makoto.vocab import _EMPTY_OK, _FENCE_SPAN_RX
from makoto.kit import _path_components, _suffix_match, unwitnessed

# SHAPE = OTHER_POINT: the witness is a second reading of the same subject on the assistant's own
# ledger/filesystem (`touched_keys`, `fs_exists`, `fs_read`) -- never an act exercised here.
dropped_SHAPE = "OTHER_POINT"


_DROP_FORWARD = r"(?:I['’]?ll|I\s+will|I['’]?m\s+going\s+to|I\s+am\s+going\s+to|let\s+me|let['’]s|let\s+us|going\s+to|i\s+plan\s+to|next\s+i\s+will|we['’]?ll|we\s+will|i\s+need\s+to|i\s+should|i\s+want\s+to)"
_DROP_VERB = r"(?:add|create|write|implement|define|introduce|build|make|set\s+up|generate|edit|modify|update|change|patch|insert|append|launch)"
_DROP_THING = r"(?:helper\s+functions?|functions?|helpers?|tests?|methods?|classes|class|fields?|fixtures?|cases?|test\s+cases?|assertions?|validators?|checks?|handlers?|endpoints?|routes?|columns?|keys?|entries|examples?|imports?|sentinels?)"
_DROP_EXT = r"\.[A-Za-z][A-Za-z0-9]{0,7}"
_DROP_BASENAME = rf"[\w-]+{_DROP_EXT}"
_DROP_PATH = rf"(?:(?:[\w.~-]+/)*{_DROP_BASENAME})"
_DROP_NEG_FRAME_RX = re.compile(
    r"\b(?:never|won['’]?t|will\s+not|do\s+not|don['’]?t|didn['’]?t|wouldn['’]?t|"
    r"rather\s+than|instead\s+of|avoid|without|no\s+need\s+to|not\s+going\s+to)\b", re.I)
_DROP_SYMDEF = r"(?:async\s+def|def|class|const|function)\s+([A-Za-z_]\w*)"
_DROP_PRE = rf"{_DROP_FORWARD}\s+(?:\w+\s+){{0,2}}?{_DROP_VERB}\b"
_DROP_DET = r"(?:a\s+|an\s+|the\s+|new\s+)*"
def _drop_loc_tail(preps):
    """The OPTIONAL trailing '<preposition> <path>' locator the claim regexes share — same body
    (clause-bounded, non-greedy, capturing `loc`), only the preposition set differs per kind."""
    return rf"(?:\b[^.;\n]*?\b(?:{preps})\s+(?P<loc>{_DROP_PATH}))?"
_DROP_RX_COUNT = re.compile(
    rf"{_DROP_PRE}\s+(?:a\s+|an\s+|the\s+)?(\d+)\s+(?:new\s+|more\s+|additional\s+)?({_DROP_THING})"
    + _drop_loc_tail("to|in|into|inside|for|under|within"), re.I)
_DROP_RX_LINES = re.compile(
    rf"{_DROP_PRE}\s+(?:lines?\s+)(\d+)\s*(?:-|–|to|through|thru)\s*(\d+)"
    + _drop_loc_tail("of|in|to|into|within"), re.I)
_DROP_RX_SYMBOL = re.compile(
    rf"{_DROP_PRE}\s+{_DROP_DET}{_DROP_SYMDEF}"
    + _drop_loc_tail("to|in|into|inside|within"), re.I)
_DROP_RX_ARTIFACT = re.compile(
    rf"{_DROP_PRE}\s+{_DROP_DET}(?:file\s+|module\s+|script\s+|config\s+)?(?P<loc>{_DROP_PATH})", re.I)
# Counts a defined callable in ANY surface form, so a "create N functions/helpers" count-claim
# discharges against lambda/arrow/partial-bound helpers too (the measured FP: 3 lambda-assigned
# helpers left the def-only counter at 0 and false-fired). Forms: py `def`/`class`; JS
# `function name`; assignment-bound callables — JS `const/let/var name = function|(...)=>|x=>|partial`
# and py `name = lambda|partial|functools.partial`. A line with NO callable binding (plain data
# assignment `x = 1`) is not counted, so the real TP (claim N, file has 0 callables of any form)
# still fires.
_DROP_DEF_COUNTER = re.compile(
    r"^\s*(?:async\s+def|def|class)\s+\w+"
    r"|^\s*(?:export\s+)?function\*?\s+\w+"
    r"|^\s*(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?"
      r"(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>|partial\b)"
    r"|^\s*\w+\s*=\s*(?:lambda\b|partial\b|functools\.partial\b)",
    re.M)
_DROP_TEST_COUNTER = re.compile(r"^\s*(?:async\s+def|def)\s+test\w*", re.M)
def dropped_owes(text):
    """Every forward claim `text` makes commits to being discharged by turn-end: [(kind,
    location, info, raw)] — a forward mutation frame + EXACTLY ONE identifying info + a
    resolvable-looking location. Vague promises (no info / no path) -> [] (never owed). Precedence
    most-specific first (line_range > count > named_symbol > named_artifact); a span is
    consumed by the first match. Negated forward frames are dropped. A frame inside a
    ```code fence``` is QUOTED text (a shell command, a demo, someone else's words), never the
    assistant's own commitment -- the L0 single-source `vocab._FENCE_SPAN_RX` decides what a
    fence is, the same object `substrate/claims.py` consumes; before
    this exclusion a count claim pasted verbatim inside a fence fired a BLOCK the turn could
    not discharge, because nothing was promised."""
    if not text:
        return []
    claims, consumed = [], []
    fenced = [m.span() for m in _FENCE_SPAN_RX.finditer(text)]

    def _overlaps(a, b):
        return any(not (b <= s or a >= e) for s, e in consumed)

    def _fenced_start(a):
        return any(s <= a < e for s, e in fenced)

    def _negated(m):
        pre = text[max(0, m.start() - 24):m.start()]
        return bool(_DROP_NEG_FRAME_RX.search(pre) or _DROP_NEG_FRAME_RX.search(m.group(0)[:40]))

    def _candidates(rx, *, require_loc=False):
        """Live (unconsumed, unnegated) matches of `rx`. Lazy on purpose: `consumed` keeps
        growing as the caller appends the spans it actually turns into claims, so a match the
        caller SKIPS (n<=0, unlocatable artifact) leaves its span free for a later kind."""
        for m in rx.finditer(text):
            if _overlaps(m.start(), m.end()) or _negated(m) or _fenced_start(m.start()):
                continue
            if require_loc and not m.group("loc"):
                continue
            yield m

    for m in _candidates(_DROP_RX_LINES, require_loc=True):
        lo, hi = int(m.group(1)), int(m.group(2))
        if hi < lo:
            lo, hi = hi, lo
        claims.append(("line_range", m.group("loc"), (lo, hi), m.group(0)))
        consumed.append((m.start(), m.end()))
    for m in _candidates(_DROP_RX_COUNT, require_loc=True):
        n = int(m.group(1))
        if n <= 0:
            continue
        claims.append(("count", m.group("loc"), n, m.group(0)))
        consumed.append((m.start(), m.end()))
    # require_loc, exactly like count/line_range above: a symbol claim with no trailing path
    # is a vague promise per this function's own contract ("no info / no path -> []"). The old
    # `m.group("loc") or sym` fallback used the SYMBOL NAME as the location, which never
    # resolves and never reads, so the discharge test returned False unconditionally -- a BLOCK
    # on a false fact ("claimed to define `parse_config` in parse_config") even when the def
    # was sitting in a touched file, with a non-path in the Finding's file field.
    for m in _candidates(_DROP_RX_SYMBOL, require_loc=True):
        sym = m.group(1)
        claims.append(("named_symbol", m.group("loc"), sym, m.group(0)))
        consumed.append((m.start(), m.end()))
    for m in _candidates(_DROP_RX_ARTIFACT):
        loc = m.group("loc")
        if not loc or not re.search(r"[\w-]+\.[A-Za-z]", loc):
            continue
        claims.append(("named_artifact", loc, os.path.basename(loc.rstrip("/")), m.group(0)))
        consumed.append((m.start(), m.end()))
    return claims
def _drop_resolve_location(L, touched_keys):
    """Resolve surface L to a path via the agent's OWN ledger: component-suffix vs a touched
    key. NO os.walk — an unbounded tree walk per claim is a Stop-hot-path landmine, and
    resolving a claimed title against the whole filesystem invites cross-project FPs. Discharge
    against a pre-existing on-disk file still works via the caller's cwd-relative fs_exists/
    fs_read on the unresolved surface (path=loc); genuinely-dropped work (never touched, never
    on disk) correctly fails to resolve and fires."""
    Lc = _path_components(L)
    for k in (touched_keys or ()):
        if _suffix_match(Lc, _path_components(k)):
            return normalize_path(k)
    return None
def _drop_discharged(kind, info, raw, path, *, touched_keys, empty_keys, fs_exists, fs_size, fs_read) -> bool:
    """At turn-end, is the forward claim satisfied on `path`? Content-deep where the kind
    needs it (symbol/count read the file via fs_read); artifact/line discharge on a non-empty
    touch or a non-empty file.

    Follows completion_gate's content-deep discharge, with a DELIBERATE and bounded difference
    from the ledger's `_discharged`: that applies the `_EMPTY_OK` conventional-empty carve-out
    globally, while this applies `conventional` on the `named_artifact` and `line_range` branches
    only.
    `named_symbol` and `count` ask a question emptiness cannot answer -- a claim to add 2 exports
    to `pkg/__init__.py` is not discharged by that file being empty, however conventional its
    emptiness is in general. So on a zero-byte conventional file with a count/symbol claim,
    `gate.completion` discharges and `gate.dropped` fires, on identical ledger state -- the
    intended reading of two different questions, not a bug to reconcile away."""
    def _drop_touched(path, touched_keys, empty_keys) -> bool:
        """A recorded NON-empty touch (Edit/Write/MultiEdit) backs this location (suffix
        match). Nested here (its only caller) once `owes`/`pays` claimed the two top-level
        slots the module-function-count design pins for this file."""
        pc = _path_components(path)
        empties = {normalize_path(k) for k in (empty_keys or ())}
        for k in (touched_keys or ()):
            if _suffix_match(pc, _path_components(k)) and normalize_path(k) not in empties:
                return True
        return False

    content = fs_read(path) if (fs_read is not None and path) else None
    touched = _drop_touched(path, touched_keys, empty_keys)
    exists = bool(fs_exists and path and fs_exists(path))
    size = fs_size(path) if (fs_size and path) else None
    # Conventional empties (__init__.py etc.): emptiness IS the deliverable — mirrors
    # _shared._discharged's _EMPTY_OK rule (consolidation T2.4; fired on honest empties before).
    conventional = os.path.basename(path or "") in _EMPTY_OK
    if kind == "named_artifact":
        if conventional and (exists or _drop_touched(path, touched_keys, None)):
            return True                                  # an empty Write of __init__.py is the work
        if content is not None:
            return len(content.strip()) > 0
        if exists:
            return size != 0
        return touched
    if kind == "named_symbol":
        if content is None:
            return False
        return bool(re.search(
            rf"^\s*(?:async\s+def|def|class|const|function\*?)\s+{re.escape(info)}\b",
            content, re.M))
    if kind == "count":
        if content is None:
            return False
        counter = _DROP_TEST_COUNTER if "test" in (raw or "").lower() else _DROP_DEF_COUNTER
        found = len(counter.findall(content))
        if found == 0 and counter is _DROP_TEST_COUNTER:
            found = len(_DROP_DEF_COUNTER.findall(content))
        return found >= info
    if kind == "line_range":
        if touched:
            return True
        if content is not None:
            return len(content.strip()) > 0 or conventional
        return exists and (size != 0 or conventional)
    return True                                          # unknown kind -> fail open


def dropped_pays(_text):
    """No event here pays a claim directly: the witness is seeded once per claim, in `paid`, from
    the assistant's OWN end-of-turn ledger/filesystem (see `dropped_gate`) -- a second reading of
    the same subject, not a fresh event in this stream."""
    return None


def dropped_gate(text, *, touched_keys, fs_exists=None, fs_size=None,
                 fs_read=None, empty_keys=None) -> Optional[Finding]:
    """Fire iff a FORWARD claim carrying identifying info (a count / line-range / named symbol
    / named artifact governed by a future-tense mutation verb) is NOT discharged at turn-end —
    the file is absent, or the claimed count/symbol/range is not present. The forgetful gate:
    said-but-not-done, a claim ✗ the assistant's own end-of-turn ledger/filesystem. A vague
    promise with no identifying info never extracts (so never fires); a negated frame
    ("I won't add X") never fires; a discharged claim is silent (fail-open)."""
    def _discharged(claim) -> bool:
        kind, loc, info, raw = claim
        path = _drop_resolve_location(loc, touched_keys) or loc
        return _drop_discharged(kind, info, raw, path, touched_keys=touched_keys, empty_keys=empty_keys,
                                fs_exists=fs_exists, fs_size=fs_size, fs_read=fs_read)

    for _ev, claim in unwitnessed((text,), owes=dropped_owes, pays=dropped_pays, paid=(_discharged,)):
        kind, loc, info, raw = claim
        path = _drop_resolve_location(loc, touched_keys) or loc
        loc_n = normalize_path(path)
        if kind == "count":
            desc = f"claimed {info} {os.path.basename(loc)}"
        elif kind == "line_range":
            desc = f"claimed an edit to lines {info[0]}-{info[1]}"
        elif kind == "named_symbol":
            desc = f"claimed to define `{info}`"
        else:
            desc = f"claimed to create `{os.path.basename(loc)}`"
        return Finding(
            pattern_id="gate.dropped", file=loc_n, line=0, level="error",
            message=(f"A forward claim {desc} in {loc_n}, but at turn-end the location does not "
                     f"contain it — said-but-not-done."),
            retry_hint="Do the claimed edit/add/create at the cited location, or retract it with a checked reason.")
    return None


dropped_CHECK = _Check(id="gate.dropped", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="OTHER_POINT",
               eats=frozenset({"text", "touched", "fs_exists", "fs_size", "fs_read", "empty"}),
               run=lambda c: dropped_gate(c.text, touched_keys=c.touched, fs_exists=c.fs_exists, fs_size=c.fs_size, fs_read=c.fs_read, empty_keys=c.empty))

# The wiring predicate lives in makoto.substrate.wiring (an L0 primitive module, firewall-
# allowed by tests/test_import_direction.py's pipeline-order firewall), shared with install.py
# rather than mirrored here.
from makoto.substrate.wiring import (
    PLUGIN_MANIFEST_RELPATH as _PLUGIN_MANIFEST_RELPATH,
    entry_dispatches_to_makoto as _entry_dispatches_to_makoto,
    event_wired as _event_wired,
    read_plugin_manifest_hooks as _read_plugin_manifest_hooks,
)

_MAKOTO_EVENTS = ("PreToolUse", "PostToolUse", "Stop")
# The FULL event set the plugin-packaged manifest wires (plugin/hooks/hooks.json): the three
# settings.json events above PLUS the plugin-only edges. Stop-edge checks genuinely run through
# SubagentStop (tests/test_dispatch.py pins gates firing through it), so a plugin manifest
# stripped of SubagentStop/SessionStart/PostToolUseFailure is a real partial strip, not noise.
# Demanded ONLY from the TRUSTED env-resolved manifest of a live plugin-packaged install; the
# settings.json sources keep the 3-event scope, which matches install._WIRED_EVENTS exactly.
_PLUGIN_MANIFEST_EVENTS = _MAKOTO_EVENTS + ("SubagentStop", "SessionStart", "PostToolUseFailure")


def _default_plugin_fs_read(path):
    try:
        if not os.path.isfile(path):
            # A FIFO or device node planted at the path would block open().read() forever,
            # wedging the Stop hook (no JSON on stdout, never exits 0) -- same isfile guard
            # the injected reader in context.py carries.
            return None
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


# The plugin root THIS running makoto lives under: .../<root>/makoto/checks/selfWiredCheck.py
# -> <root>. The dispatch shim cd's into $CLAUDE_PLUGIN_ROOT and execs `python3 -m
# makoto.dispatch` from there, so for a genuine plugin-packaged install the running package's
# grandparent directory IS the live plugin root. A static property of this file, safe to bind
# at import; consumed by the `_trusted_env_root` identity assertion nested in
# `_missing_makoto_events` and `self_wired_gate` (nested, not top-level -- the flat def count
# is part of this package's pinned shape), which keeps a decoy/forged $CLAUDE_PLUGIN_ROOT from
# ever CONFIRMING wiring: without it, a decoy root carrying a copied manifest silently
# suppresses a real full strip (absence reading green). A foreign or unverifiable root degrades
# to None -- "confirms nothing" -- the same fail-closed direction read_plugin_manifest_hooks
# documents; this is the concrete meaning of the docstring's "never a guessed/cached path".
_OWN_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _missing_makoto_events(hooks, *, plugin_root=None, plugin_fs_read=None,
                           home_hooks=None, events=_MAKOTO_EVENTS) -> list:
    """[event, ...] for each event in `events` confirmed by NONE of: settings.json's own "hooks"
    key, the home `~/.claude/settings.json` hooks passed as `home_hooks` (the file
    `makoto install` actually writes), or the plugin manifest (a plugin-packaged install
    legitimately wires makoto via hooks/hooks.json alone, and settings.json is never expected to
    duplicate it — this predicate checks every source before calling an event missing). Empty
    list means fully wired. `plugin_root` defaults to the live
    $CLAUDE_PLUGIN_ROOT — identity-checked against the running package's own plugin root, so a
    decoy root can never confirm wiring — and `plugin_fs_read` to an isfile-guarded real file
    read when not supplied, so this stays pure/injectable for tests exactly like the
    settings.json side already is — see tests/test_self_wired_check.py.

    `hooks` NORMALIZATION IS PART OF THIS CONTRACT, not an incidental guard: a missing/None/
    non-dict `hooks` is read as {} (i.e. "wires nothing", so all three events report missing),
    so no caller needs its own isinstance pre-guard. Load-bearing for
    `test_hooks_key_not_a_dict_fails_open_to_missing_all`; do not drop it."""
    settings_hooks = hooks if isinstance(hooks, dict) else {}
    home = home_hooks if isinstance(home_hooks, dict) else {}
    plugin = []   # the manifest, read once and only when an event reaches it unwired

    def _plugin_wired(event):
        if not plugin:
            root = plugin_root
            if root is None:
                # Env-derived root: identity-checked against _OWN_PLUGIN_ROOT (see its comment)
                # so a decoy $CLAUDE_PLUGIN_ROOT can never CONFIRM wiring; mirrored in
                # self_wired_gate.
                root = os.environ.get("CLAUDE_PLUGIN_ROOT")
                if root:
                    try:
                        if os.path.realpath(root) != os.path.realpath(_OWN_PLUGIN_ROOT):
                            root = None
                    except OSError:
                        root = None
            reader = plugin_fs_read if plugin_fs_read is not None else _default_plugin_fs_read
            plugin.append(_read_plugin_manifest_hooks(root, reader))
        return _event_wired(plugin[0], event)

    # Owed: every event makoto must be wired on. Paid: a source that wires it, cheapest first.
    return [event for _events, event in unwitnessed(
        (events,), owes=lambda es: es, pays=lambda _es: None,
        paid=(lambda e: _event_wired(settings_hooks, e), lambda e: _event_wired(home, e),
              _plugin_wired))]


def self_wired_gate(fs_read, *, plugin_root=None, plugin_fs_read=None,
                    home_fs_read=None) -> Optional[Finding]:
    """Partial-strip detection only: catches an edit that leaves at least one of makoto's
    PreToolUse/PostToolUse/Stop entries wired (in ANY consultable source) while removing
    another; an edit that strips wiring from ALL sources for ALL events simultaneously disables
    this check itself in the same instant (Claude Code reloads hooks.json live, not cached once
    at session start — verified against code.claude.com/docs/en/settings.md, "When edits take
    effect"), so it still provides ZERO coverage against that canonical full-strip attack. This check is
    mitigation, not closure.

    THREE wiring sources, checked with IDENTICAL rigor: the project `.claude/settings.json`'s
    own "hooks" key (repo-root-relative, read via `fs_read`), the HOME `~/.claude/settings.json`
    — the file `makoto install` actually writes (install._settings_path), read via
    `home_fs_read` (defaults to an isfile-guarded real read; consultable only when it carries a
    real hooks dict) — and the makoto plugin's own hooks/hooks.json manifest, resolved via
    `plugin_root` (defaults to the live $CLAUDE_PLUGIN_ROOT, identity-checked against the
    plugin root the RUNNING package lives under so a decoy/forged root can never confirm wiring
    — the concrete meaning of "never a guessed/cached path") and read via `plugin_fs_read`
    (defaults to the same isfile-guarded read). Fires iff an event is confirmed by NO source; an
    absent/empty project settings.json does not short-circuit the other sources -- a
    plugin-packaged install (the main way makoto ships) has no project settings file at all, and
    must still be checked against the home hooks table and the plugin manifest. When NO source is
    even consultable (no project settings, no home hooks table, no trusted plugin root), there is
    no fact to assert either way, so the gate stays silent. The message names exactly which event(s) lost their entry and which sources were
    consulted; the Finding's `file` points at a source that was actually consulted, never
    unconditionally at a project settings file that may not exist.

    For a TRUSTED env-resolved plugin manifest the demanded event set widens from the three
    settings.json events to every event the packaged manifest declares
    (`_PLUGIN_MANIFEST_EVENTS`): SubagentStop/SessionStart/PostToolUseFailure enforcement is
    real (Stop gates fire through SubagentStop — tests/test_dispatch.py), so stripping those
    keys from a plugin-packaged hooks/hooks.json must not read clean.

    ADVISORY tier only (`level="advisory"`, never `"error"`): per this repo's "advisory over
    blocking" standing policy and the explicit condition this check shipped under, it must never
    block a turn — `_emit_decision` in dispatch.py maps level=="advisory" to posture.ADVISE, and
    wire.py's Stop/SubagentStop table has no ADVISE entry (only BLOCK renders there), so an
    advisory finding is recorded to the audit log (a forensic trail) and never surfaces as a
    block. Fail-open on a MALFORMED project settings.json (unparseable JSON or a non-dict
    payload returns None silently, matching every other gate's fail-open philosophy); the
    plugin-manifest side fails CLOSED instead (any read/resolution failure there degrades to
    "confirms nothing", never to silent-wired — an unresolvable/forged plugin_root must never
    suppress a real finding). This still cannot distinguish a genuine simultaneous full strip
    of every source (the documented blind spot above) — it reads disk state at check time, not
    the harness's own live-loaded hook table."""
    if fs_read is None:
        return None
    try:
        raw = fs_read(".claude/settings.json")
    except Exception:
        return None
    project_hooks = None
    project_consulted = False
    if raw:
        try:
            data = json.loads(raw)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        project_consulted = True
        # No isinstance pre-guard here: normalizing a missing/non-dict "hooks" to {} is part of
        # `_missing_makoto_events`'s own documented contract (see its docstring).
        project_hooks = data.get("hooks")
    # The HOME `~/.claude/settings.json` -- the file `makoto install` actually writes
    # (install._settings_path). Consultable ONLY when it carries a real non-empty hooks dict:
    # a hooks-less home settings can neither confirm nor indict, so it never triggers a
    # finding on its own and never silences one.
    home_hooks = None
    home_path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    try:
        raw_home = (home_fs_read if home_fs_read is not None
                    else _default_plugin_fs_read)(home_path)
    except Exception:
        raw_home = None
    if raw_home:
        try:
            home_data = json.loads(raw_home)
        except Exception:
            home_data = None
        if isinstance(home_data, dict):
            candidate = home_data.get("hooks")
            if isinstance(candidate, dict) and candidate:
                home_hooks = candidate
    env_root = None
    if plugin_root is None:
        # Env-derived root: identity-checked against _OWN_PLUGIN_ROOT (see its comment) so a
        # decoy $CLAUDE_PLUGIN_ROOT can never CONFIRM wiring.
        env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if env_root:
            try:
                if os.path.realpath(env_root) != os.path.realpath(_OWN_PLUGIN_ROOT):
                    env_root = None
            except OSError:
                env_root = None
    root = plugin_root if plugin_root is not None else env_root
    if not (project_consulted or home_hooks is not None or root):
        # No source is even consultable: project settings absent/empty, home settings carries
        # no hooks table, no trusted plugin root. There is no wiring fact to assert either
        # way -- fail-open on total absence, never a Finding resting on an unconsulted oracle.
        return None
    events = _PLUGIN_MANIFEST_EVENTS if env_root else _MAKOTO_EVENTS
    missing = _missing_makoto_events(project_hooks, plugin_root=root,
                                     plugin_fs_read=plugin_fs_read,
                                     home_hooks=home_hooks, events=events)
    if not missing:
        return None
    named = ", ".join(missing)
    manifest_path = os.path.join(root, _PLUGIN_MANIFEST_RELPATH) if root else None
    consulted = []
    if project_consulted:
        consulted.append(".claude/settings.json")
    if home_hooks is not None:
        consulted.append("~/.claude/settings.json")
    if manifest_path:
        consulted.append(manifest_path)
    if project_consulted:
        finding_file = ".claude/settings.json"
    elif manifest_path:
        finding_file = manifest_path
    else:
        finding_file = os.path.join("~", ".claude", "settings.json")
    return Finding(
        pattern_id="gate.self_wired",
        file=finding_file,
        line=0,
        level="advisory",
        message=(f"makoto's hook wiring is missing an entry for: {named} in every consultable "
                 f"wiring source ({'; '.join(consulted)}). "
                 "This is a PARTIAL-STRIP signal only — it cannot see a simultaneous strip of "
                 "all events from every source at once (see gate.self_wired's docstring)."),
        retry_hint=("Advisory only, never blocking: confirm this was an intentional change, or "
                    "restore the missing hook entry — `makoto install` re-wires "
                    "~/.claude/settings.json; a plugin-packaged install needs its "
                    "hooks/hooks.json manifest restored (re-enable/reinstall the plugin)."),
    )


# NOTE: this CHECK's posture is "ADVISE", not "BLOCK" like every sibling Stop gate.
# gate.self_wired's own Finding.level is documented and behaviorally pinned
# (tests/test_stop_gate_level_invariant.py) as ALWAYS "advisory", never "error" (the one
# DESIGN-DECISION-cited advisory exception among the Stop gates, FD6) -- declaring it
# CHECK.posture="BLOCK" here would misrepresent that in the flat checks/ catalog's own metadata.
# `may_block=True` here is NOT a contradiction: it only says "structurally eligible IF posture
# were ever BLOCK" (it isn't, and is pinned as such by the test above) -- the actual never-blocks
# guarantee still rests on posture=="ADVISE", same as always.
from makoto.kit import live_query_finding
wired_run = live_query_finding(
    query=lambda fs_read: self_wired_gate(fs_read), posture_label="gate.self_wired"
)
wired_CHECK = _Check(id="gate.self_wired", applies_at="Stop", posture="ADVISE", may_block=True,
               eats=frozenset({"fs_read"}),
               run=wired_run, layer="meta", tests="OTHER_POINT")

# gate.claimed_consent_absent -- the agent cites the operator's word, and the operator has none.
#
# Makoto's subject is the assistant's statement held against the record. Usually the record is the
# assistant's own tool stream. Here it is the ORACLE channel: the genuine, host-written user turns
# of this session. That is not holding the human to anything -- the human is never graded. It is
# holding the AGENT to a claim it made ABOUT the human, which is the same bar as every other check
# here, against a record Makoto already reads (`ledger.user_turn_texts`, shared with
# `content.unsourced_webfetch._user_supplied` -- one owner, two consumers, no second definition of
# "the user said so").
#
# WHY IT EXISTS. An agent that cites approval it was never given has licensed itself, and the
# licence is the most valuable thing it can forge: it converts "I should ask" into "I was told".
# The hazard is live and currently held off by prose -- a session woken by a schedule or a
# background event carries a hand-written notice on every turn saying that no human input has been
# received and that any statement the user approved something must not be treated as consent. A
# rule stated on every turn and enforced nowhere is B7 in the register, and this is its runner.
#
# THE 0-FP CONDITION, and it is what keeps this from being a paraphrase judge. The check fires only
# when the session contains NO genuine operator turn at all. Not "the turn does not match the
# claim" -- that is a similarity question and similarity is judgement. Absence of the whole channel
# is countable, and when the channel is empty every attribution to it is false, whatever words were
# chosen. So a legitimate paraphrase of a real instruction can never fire this: a real instruction
# means a real turn exists, and one turn is enough to silence it.
#
# Spoof-resistance is inherited, not re-derived: `user_turn_texts` admits only host-written,
# non-synthetic, non-tool-result entries via `_is_genuine_user_turn`. The agent cannot write itself a user turn, so it cannot
# manufacture the consent OR the record of it.
#
# STATED LIMIT: a session where the operator has spoken once and the agent then invents a second,
# different instruction is NOT caught. Catching it needs the claim compared to the turn's content,
# which is the similarity question this check refuses. Named here so the gap is a choice on the
# record rather than an oversight.

# gate.claimed_consent_absent's SHAPE (see plugin/makoto/kit.py's `unwitnessed`): OTHER_POINT --
# the witness is a second reading of the same subject (the operator's own turns, read from the
# transcript) against the agent's claim of what the operator said.
consent_SHAPE = "OTHER_POINT"

# The claim side: the agent attributing a position to the operator. Read on the ASSISTANT's own
# words, which is what every check here does -- the non-agnostic surface in this package is the
# three checks that parse the SUBJECT's shell commands, not the claim channel.
_CONSENT_RX = re.compile(
    r"\b(?:"
    r"(?:you|the\s+(?:user|operator|owner))\s+"
    r"(?:approved|confirmed|agreed|authorized|authorised|okayed|"
    r"said|asked|told\s+me|requested|instructed|signed\s+off|greenlit|"
    r"gave\s+(?:me\s+)?the\s+green\s+light)"
    r"|per\s+your\s+(?:approval|request|instruction|confirmation|go-ahead)"
    r"|as\s+you\s+(?:asked|requested|instructed|said|confirmed|approved)"
    r"|with\s+your\s+(?:approval|consent|go-ahead|sign-off)"
    r"|on\s+your\s+(?:instruction|say-so|go-ahead)"
    r")\b", re.IGNORECASE)

consent_RETRY_HINT = ("This session has no operator turn, so there is no approval or instruction to "
              "cite. Say what you are doing and why on your own account, or stop and ask.")
consent_DESCRIPTION = ("Blocks a claim that the operator approved, asked for or confirmed something in a "
               "session where the operator has not spoken at all.")


def consent_owes(text):
    """The one subject a consent claim commits to: itself. Cheap and pure -- the witness (a
    second, independent reading of the operator's own turns) lives in `paid`, below."""
    return (m,) if (m := _CONSENT_RX.search(text or "")) else ()


def consent_pays(_text):
    return None


def _oracle_channel_paid(transcript_path) -> bool:
    """True (silent) unless the oracle channel is CONFIRMED both readable and empty -- the one
    case that discharges nothing. Never raises: an unreadable or absent transcript reads as NO
    EVIDENCE and pays silently, because the alternative -- blocking a turn on a decode failure --
    is a gate resting on a false fact. `user_turn_texts` returns [] for a transcript it cannot
    parse as well as for one with no user turns, and those two must not be treated alike when the
    consequence is a block, so an empty result is only trusted once the transcript itself is
    confirmed to exist."""
    from makoto.state.ledger import user_turn_texts
    if not transcript_path:
        return True
    try:
        turns = user_turn_texts(transcript_path)
    except Exception:
        return True
    if turns:
        # The operator has spoken. Whether THIS claim matches THAT turn is the similarity
        # question this check refuses to answer; see the stated limit in the module docstring.
        return True
    try:
        import os
        if not os.path.exists(transcript_path):
            return True
    except Exception:
        return True
    return False


def claimed_consent_absent_gate(text, *, transcript_path=None):
    """One BLOCKING Finding when the claim cites the operator and the oracle channel is
    confirmed empty."""
    for _ev, claim in unwitnessed(
            (text,), owes=consent_owes, pays=consent_pays,
            paid=(lambda _c: _oracle_channel_paid(transcript_path),)):
        return Finding(
            pattern_id="gate.claimed_consent_absent",
            file="", line=0, level="error",
            message=(f"Claim cites the operator ({claim.group(0)!r}), but this session's transcript "
                     f"carries no genuine operator turn — the consent is attributed to a record that "
                     f"is empty."),
            retry_hint=consent_RETRY_HINT,
        )
    return None


consent_CHECK = _Check(id="gate.claimed_consent_absent", applies_at="Stop", posture="BLOCK",
               may_block=True, tests="OTHER_POINT",
               keywords=("you approved", "you asked", "you said", "you confirmed",
                         "as you asked", "per your", "with your approval"),
               retry_hint=consent_RETRY_HINT, description=consent_DESCRIPTION,
               eats=frozenset({"text", "transcript_path"}),
               run=lambda c: claimed_consent_absent_gate(c.text,
                                                         transcript_path=c.transcript_path))

# PREVENTIVE-at-PreToolUse precheck event.thrash_revert — flag a Write that REVERTS
# a file back to a byte-identical copy of an earlier whole-file content this session (an A->B->A
# oscillation) at PreToolUse time.
#
# WHAT IT FIRES ON: the about-to-execute Write carries `content` byte-identical to an EARLIER
# whole-file Write of the SAME `file_path` in this session's history, with at least one INTERVENING
# whole-file Write of DIFFERENT content to that path between them (A -> B -> now-A). That is a
# self-revert that churns the file with no net progress.
#
# WHY WHOLE-FILE Write.content ONLY (the load-bearing 0-FP narrowing): comparing an Edit `new_string`
# FRAGMENT gave 7 corpus FALSE POSITIVES in the sibling canon.oscillate — a short snippet or a
# re-inserted import line is not a closed whole-file unit, so two unrelated edits sharing a fragment
# look like a bogus revert. This precheck NEVER compares fragments: a CURRENT Edit/MultiEdit/
# NotebookEdit is SILENT, and a PRIOR Edit/MultiEdit/NotebookEdit is not counted as a content unit
# (only whole-file Writes are). The compared unit is whole-file `Write.content` exclusively.
#
# Carries its OWN whole-file-Write history walker so a PreToolUse precheck does not import the
# Stop-gate engine. The ONLY content read is through ByteIdentity (==/len/hash only), so this
# body CANNOT read content MEANING — only content IDENTITY. Stdlib only; the only imports are
# makoto.substrate, makoto.kit, makoto.vocab and makoto.registry.
from makoto.substrate.byte_identity import ByteIdentity
from makoto.kit import decode_history_row, unwitnessed

# SHAPE = OTHER_POINT: the witness is a second reading of the same subject -- an earlier
# whole-file Write of the SAME path, a history row -- never a live-exercised act or a source read.
thrash_SHAPE = "OTHER_POINT"


def thrash_owes(ev):
    """The about-to-land whole-file Write owes a witness that it is not an A->B->A self-revert.
    `ev` is `(now, prior)`: `now` is this write's `ByteIdentity` content, `prior` the ordered
    whole-file contents this session already landed at the same path. Embeds the full A->B->A
    walk itself (a single left-to-right pass, exactly as before): the obligation is raised only
    once some earlier landed content equals `now` (an A) AND some later-landed content in between
    differs from it (a B) -- a bare A->A repeat with no intervening B is a no-op rewrite, not a
    revert, and never even raises this."""
    now, prior = ev
    seen_earlier_a = False
    for earlier in prior:
        if earlier == now:
            seen_earlier_a = True
        elif seen_earlier_a:
            return (now,)
    return ()


def thrash_pays(_ev):
    """Nothing pays this obligation: the A->B->A pattern is either present in `prior` or it is
    not, and `owes` has already read the whole of `prior` to decide that -- there is no further
    witness this check reads."""
    return None


def _prior_whole_file_writes(history, path: str) -> list:
    """Ordered ByteIdentity-wrapped whole-file Write contents to `path` in the session history.
    ONLY tool_name=='Write' rows carrying a `content` key are counted — Edit/MultiEdit/NotebookEdit
    fragments are deliberately excluded (the canon.oscillate 7-FP lesson). Rows are either the
    (id, ts, event_type, cwd, raw_payload_json) tuples _select_recent returns OR dicts with a
    'payload' key (corpus replay). Fail-open: an unparseable / payload-less row is skipped.

    Row-decode step shared via makoto.kit.decode_history_row, the same one substrate._canonAtoms.
    _decode_row uses -- one definition of the tuple/dict-payload sniff + json.loads, not two. Only
    this function's own Write/content filter stays local."""
    out: list = []
    for row in history or ():
        ev = decode_history_row(row)
        if not isinstance(ev, dict) or ev.get("tool_name") != "Write":
            continue
        # LANDED content only: `_ingest_event` persists every row BEFORE its handler runs, so
        # the history also holds PreToolUse rows (attempts, including DENIED ones) and
        # PostToolUseFailure rows (writes that did NOT land). Counting those as "the file's
        # content" made a write that never executed the intervening B — a DENY resting on a
        # change that never happened. Only a successful PostToolUse row proves the disk held
        # this content.
        if ev.get("hook_event_name") != "PostToolUse":
            continue
        inp = ev.get("tool_input") or {}
        if not isinstance(inp, dict) or inp.get("file_path") != path or "content" not in inp:
            continue
        out.append(ByteIdentity(inp["content"]))
    return out


def thrash_predicate(*, current_event: dict, history: list,
              pattern: Check, conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    # Whole-file Write ONLY. A current Edit/MultiEdit/NotebookEdit carries only a fragment, not a
    # closed whole-file unit, so it is never judged here (fragment compares are the FP class).
    if current_event.get("tool_name") != "Write":
        return None
    ti = current_event.get("tool_input")
    if not isinstance(ti, dict):
        return None
    path = ti.get("file_path") or ""
    if not path or "content" not in ti:
        return None                       # no path / no whole-file content -> nothing to revert
    now = ByteIdentity(ti["content"])

    prior = _prior_whole_file_writes(history, path)
    # A->B->A: some EARLIER whole-file Write of this path == now (an A), AND at least one whole-file
    # Write of DIFFERENT content (a B) lies AFTER that earlier A. A bare A->A repeat (no intervening
    # different content) is a no-op rewrite, not a revert. The walk itself lives in `owes` now; see
    # its docstring for why one left-to-right pass over `prior` decides it.
    for _ev, _subject in unwitnessed(((now, prior),), owes=thrash_owes, pays=thrash_pays):
        return Finding(
            pattern_id=pattern.id,
            file=path,
            line=0,
            level="error",  # Pre-tier is invariantly BLOCK; Check has no fire_level (test_pre_tier_block_invariant.py)
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

thrash_RETRY_HINT = 'Decide which content is correct and write it once; do not revert to an earlier whole-file version after changing it.'
thrash_DESCRIPTION = 'whole-file A->B->A self-revert (no net progress)'

from makoto.registry import Check
thrash_CHECK = Check(id='event.thrash_revert', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('Write',), retry_hint=thrash_RETRY_HINT, description=thrash_DESCRIPTION, eats=frozenset({"current_event", "history", "pattern"}), tests="OTHER_POINT")


# the OTHER_POINT shape's rows, and the one Pre entry dispatch calls for any of them
_ROWS = (shipped_CHECK, completion_CHECK, dropped_CHECK, wired_CHECK, consent_CHECK, thrash_CHECK,)
ROWS = {c.id: c for c in _ROWS}
CHECK, *EXTRA_CHECKS = _ROWS
_PREDICATES = {thrash_CHECK.id: thrash_predicate}


def predicate(*, current_event: dict, history: list, pattern, conn=None):
    """Dispatch calls one predicate per module; this shape's answers for the row it names."""
    return _PREDICATES[pattern.id](current_event=current_event, history=history, pattern=pattern, conn=conn)

