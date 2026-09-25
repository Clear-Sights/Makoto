"""Plan-item store: source open PLAN/TASK-LABELED promises from prose and from the harness's own
Task tool calls, and read them back un-windowed by session.

Uses Makoto's own `plan_item_commitments` sqlite table (see db.py).

Stdlib only; no LLM, no HTTP.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

from makoto.vocab import _OFFER_COND_RX, _FIRST_PERSON_RX

# =============================================================================================
# plan-item commitments: source open PLAN/TASK-LABELED promises ("I'll finish §9.3", "next I
# need to close out Task #19") from the assistant's own text, and read them back un-windowed by
# session.
#
# A plan/task label ("§9.3", "Task #19") has no filesystem location, so discharge here is
# PURELY TEXTUAL -- a later first-person completion statement naming the same label, or an
# explicit retraction.
#
# Sourcing discipline mirrors hardened guards elsewhere (first-person, active, non-past,
# non-negated, non-conditional), scoped down for this narrower label-shaped surface, not yet
# corpus-measured for FPs.
#
# Stdlib only; no LLM, no HTTP.

# A plan/task label: "§9", "§9.3", "Task #19", "task 19". Word-bounded so it never swallows a
# surrounding sentence.
_LABEL_RX = re.compile(r"(§\s?\d+(?:\.\d+)*|\btask\s*#?\s?\d+\b)", re.IGNORECASE)
_FORWARD_VERB_RX = re.compile(
    r"\b(?:finish(?:ing)?|complet(?:e|ing)|do(?:ing)?|handl(?:e|ing)|tackl(?:e|ing)|"
    r"wrap(?:ping)?\s+up|clos(?:e|ing)\s+out|address(?:ing)?|resolv(?:e|ing)|"
    r"get(?:ting)?\s+to|work(?:ing)?\s+on|pick(?:ing)?\s+up|start(?:ing)?)\b",
    re.IGNORECASE)
_PAST_VERB_RX = re.compile(
    r"\b(?:finish(?:ed)|complet(?:ed)|done(?:\s+with)?|handl(?:ed)|tackl(?:ed)|"
    r"wrapp?ed\s+up|closed\s+out|address(?:ed)|resolv(?:ed)|landed|shipped)\b",
    re.IGNORECASE)
_NEGATED_RX = re.compile(
    r"\b(?:do not|don'?t|won'?t|will not|will never|never|not going to|never going to|"
    r"not planning to|no longer|skip(?:ping)?|never\s?mind|dropping|drop(?:ped)?|"
    r"not\s+(?:doing|finishing|completing|going\s+to))\b",
    re.IGNORECASE)
_BIND_BEFORE = 60
_BIND_AFTER = 40
# A negation immediately governing a past verb ("is not done yet", "isn't finished", "hasn't
# been completed"): a copular/auxiliary negation before the participle means the item is
# explicitly UNFINISHED -- neither a completion nor a retraction, so the item stays open.
_NEG_BEFORE_VERB_RX = re.compile(
    r"\b(?:not|never|isn'?t|aren'?t|wasn'?t|weren'?t|hasn'?t|haven'?t|hadn'?t|ain'?t)"
    r"(?:\s+(?:been|yet|quite|fully|completely|entirely|actually|really))*\s+$",
    re.IGNORECASE)
# The verb is line-initial after at most a bullet/number marker -> an imperative plan bullet
# ("- start §9.3", "1. finish §9.3"). Same line-initial convention the cut store used.
_LINE_INITIAL_RX = re.compile(r"^[\s\-*•>\d.)\]]*$")
# First sentence terminator after the label -- a '?' there marks an interrogative ("Should I
# start §9.3?"), which is an offer for approval, never a firm promise.
_SENT_END_RX = re.compile(r"[.!?\n]")


def _normalize_label(raw: str) -> str:
    """'§ 9.3' / 'Task # 19' / 'task19' -> a canonical 'section:9.3' / 'task:19' key, so the
    same item re-referenced with different spacing/case dedupes to the same commitment_key."""
    s = raw.strip().lower()
    if s.startswith("§"):
        return f"section:{s.lstrip('§').strip()}"
    digits = re.sub(r"[^\d.]", "", s)
    return f"task:{digits}"


def _first_person_governs(text: str, verb_start: int, line_start: int) -> bool:
    """True iff the clause containing the verb has a first-person subject, or the verb sits at
    the start of its line after at most a bullet/number marker (an imperative plan bullet)."""
    if verb_start < line_start:
        # The verb sits on a PREVIOUS line (the label's line_start is past it): judge the verb
        # against ITS OWN line, never a reversed/empty slice -- an empty prefix here used to
        # read third-person prose on the prior line as a line-initial imperative.
        line_start = text.rfind("\n", 0, verb_start) + 1
    prefix = text[line_start:verb_start]
    if _LINE_INITIAL_RX.match(prefix):
        return True                                   # line-initial verb -> imperative bullet
    return bool(_FIRST_PERSON_RX.search(prefix[-_BIND_BEFORE:]))


def source_plan_item_promise(text: str) -> Optional[dict]:
    """First plan/task label that is the object of a first-person, active, non-past, non-negated,
    non-conditional FORWARD promise, else None. Not yet corpus-measured for FPs."""
    if not text:
        return None
    for m in _LABEL_RX.finditer(text):
        a, b = m.span()
        line_start = text.rfind("\n", 0, a) + 1
        before_start = max(0, a - _BIND_BEFORE)
        before = text[before_start:a]
        after = text[b:b + _BIND_AFTER]
        if _NEGATED_RX.search(before) or _NEGATED_RX.search(after):
            continue                                  # "won't finish §9.3" / "skip §9.3" -> not a promise
        if _PAST_VERB_RX.search(before):
            continue                                  # "finished §9.3" -> a completion, not a promise
        vm = _FORWARD_VERB_RX.search(before)
        if not vm:
            continue                                  # label mentioned with no forward verb governing it
        if _OFFER_COND_RX.search(before[:vm.start()][-46:]):
            continue                                  # "if you want, I'll finish §9.3" -> a conditional offer
        if _OFFER_COND_RX.search(after):
            continue                                  # "I'll work on §9.3 if the tests pass" -> conditional too
        sent_end = _SENT_END_RX.search(text, b)
        if sent_end and sent_end.group() == "?":
            continue                                  # "Should I start §9.3?" -> a question, not a promise
        if not _first_person_governs(text, before_start + vm.start(), line_start):
            continue
        label = _normalize_label(m.group(1))
        line_end = text.find("\n", b)
        desc = text[line_start:line_end if line_end != -1 else len(text)].strip()
        return {"label": label, "description": desc[:200]}
    return None


def _affirmed_past_verb(window: str):
    """First _PAST_VERB_RX match in `window` NOT immediately negated ("is not done yet",
    "isn't finished", "hasn't been completed"), else None. A negated participle is an
    explicitly-unfinished statement, never a completion."""
    for vm in _PAST_VERB_RX.finditer(window):
        if _NEG_BEFORE_VERB_RX.search(window[:vm.start()]):
            continue
        return vm
    return None


def source_plan_item_completions(text: str) -> set:
    """Labels this turn's text marks COMPLETE via a first-person (or imperative bullet), active,
    non-conditional, non-negated past-tense verb governing them, or explicitly RETRACTS via a
    negation frame -- {(label, 'done'|'retracted'), ...}. The 'done' arm applies the SAME
    discipline the promise sourcer above uses (first-person governance, no conditional frame):
    "the user reported Task #19 was completed by someone else" or "once §9.3 is finished we can
    ship" is not the assistant discharging its own item."""
    if not text:
        return set()
    out = set()
    for m in _LABEL_RX.finditer(text):
        a, b = m.span()
        before_start = max(0, a - _BIND_BEFORE)
        before = text[before_start:a]
        after = text[b:b + _BIND_AFTER]
        label = _normalize_label(m.group(1))
        if _NEGATED_RX.search(before) or _NEGATED_RX.search(after):
            out.add((label, "retracted"))
            continue
        vm = _affirmed_past_verb(before)
        if vm is not None:
            verb_start = before_start + vm.start()
        else:
            vm = _affirmed_past_verb(after)
            if vm is None:
                continue                              # no affirmed completion verb governs this label
            verb_start = b + vm.start()
        if _OFFER_COND_RX.search(text[max(0, verb_start - 46):verb_start]):
            continue                                  # "once §9.3 is finished ..." -> conditional, not a discharge
        line_start = text.rfind("\n", 0, a) + 1
        if not _first_person_governs(text, verb_start, line_start):
            continue                                  # third-person/passive report -> not the assistant's own act
        out.add((label, "done"))
    return out


def commitment_key(session_id: str, label: str) -> str:
    return hashlib.sha1(f"{session_id}\x00{label}".encode("utf-8")).hexdigest()


def record_plan_item(conn, session_id: str, item: dict) -> str:
    """Persist an OPEN plan-item commitment (idempotent on commitment_key); re-opens a
    previously retracted item on re-promise, same rule `commitments.record_commitment` follows."""
    key = commitment_key(session_id, item["label"])
    conn.execute(
        "INSERT INTO plan_item_commitments (commitment_key, session_id, label, description, status) "
        "VALUES (?, ?, ?, ?, 'open') "
        "ON CONFLICT(commitment_key) DO UPDATE SET status = 'open' "
        "WHERE plan_item_commitments.status = 'retracted'",
        [key, session_id, item["label"], item["description"]])
    conn.commit()
    return key


def open_plan_items(conn, session_id: str) -> list:
    """Read OPEN plan-item commitments for a session, UN-WINDOWED."""
    rows = conn.execute(
        "SELECT commitment_key, label, description FROM plan_item_commitments "
        "WHERE session_id = ? AND status = 'open'", [session_id]).fetchall()
    return [{"commitment_key": r[0], "label": r[1], "description": r[2]} for r in rows]


def set_plan_item_status(conn, session_id: str, label: str, status: str) -> None:
    key = commitment_key(session_id, label)
    conn.execute(
        "UPDATE plan_item_commitments SET status = ? WHERE commitment_key = ?", [status, key])
    conn.commit()


def sync_plan_items(conn, session_id: str, text: str) -> None:
    """One Stop-time pass: source any new promise in `text`, then apply any completion/retraction
    `text` states, against this session's plan_item_commitments. Fail-open per-call (a DB fault
    here must never block the turn) -- callers wrap this, matching every other store's discipline."""
    promise = source_plan_item_promise(text)
    if promise:
        record_plan_item(conn, session_id, promise)
    for label, status in source_plan_item_completions(text):
        set_plan_item_status(conn, session_id, label, status)


def record_task_event(conn, session_id: str, payload: dict) -> None:
    """The GROUND-TRUTH source for the same store: the harness's own TaskCreate/TaskUpdate tool
    calls, read off the PostToolUse payload. Unlike the prose sourcer above, a Task tool call is
    an explicit, deliberate act with a stable id. Payload shapes:

      TaskCreate  PostToolUse: tool_response = {"task": {"id": "1", "subject": ...}}
      TaskUpdate  PostToolUse: tool_input  = {"taskId": "1", ...}
                               tool_response = {"success": true, "taskId": "1",
                                                "statusChange": {"from": ..., "to": ...}}

    The label is `task:<id>` -- the SAME canonical key `_normalize_label` gives a prose mention
    of "Task #<id>", so a chat promise and the real Task object dedupe into one commitment. A
    `to: completed` transition discharges it ('done'); `to: deleted` retracts it; a create (or a
    resumed session's first update to a task this store never saw) opens it. Anything else is
    not a lifecycle transition and is ignored. Fail-open: a malformed payload is a no-op."""
    tool = payload.get("tool_name", "")
    resp = payload.get("tool_response") or {}
    if not isinstance(resp, dict):
        return
    if tool == "TaskCreate":
        task = resp.get("task") or {}
        tid, subject = task.get("id"), task.get("subject", "")
        if tid:
            record_plan_item(conn, session_id,
                             {"label": f"task:{tid}", "description": str(subject)[:200]})
        return
    if tool == "TaskUpdate":
        tid = resp.get("taskId") or (payload.get("tool_input") or {}).get("taskId")
        change = resp.get("statusChange") or {}
        to = change.get("to")
        if not tid or not to:
            return
        label = f"task:{tid}"
        if to == "completed":
            set_plan_item_status(conn, session_id, label, "done")
        elif to == "deleted":
            set_plan_item_status(conn, session_id, label, "retracted")
        elif to == "in_progress":
            # A task this store never saw surfaces as open; a completed-then-resumed one must
            # also re-open, so the status is set explicitly after the upsert (which only lifts
            # 'retracted').
            record_plan_item(conn, session_id, {"label": label, "description": ""})
            set_plan_item_status(conn, session_id, label, "open")
