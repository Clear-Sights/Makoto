"""Plan-item commitments store: source open PLAN/TASK-LABELED promises ("I'll finish §9.3",
"next I need to close out Task #19") from the assistant's own text, and read them back
un-windowed by session.

Distinct from `session/commitments.py` (which sources a promise to a FILE PATH and discharges
it by checking the filesystem/touched-keys): a plan/task label ("§9.3", "Task #19") has no
filesystem location at all, so discharge here is PURELY TEXTUAL -- a later first-person
completion statement naming the same label, or an explicit retraction. This closes the gap a
real session hit: a forward commitment phrased as a section/task reference, never a file path,
was silently dropped and never appeared in ANY commitment store because `commitments.py`'s
sourcer requires a file-shaped location and found none.

Sourcing discipline mirrors `commitments.py`'s hardened guards (first-person, active, non-past,
non-negated, non-conditional) at the same rigor tier, scoped down for this narrower label-shaped
surface rather than re-deriving from a real-session FP corpus this module has not been measured
against yet -- see the module docstring's own caveat below.

Stdlib only; no LLM, no HTTP.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

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
_OFFER_COND_RX = re.compile(r"\b(?:if|once|unless|assuming|provided|whether|in case)\b",
                            re.IGNORECASE)
_FIRST_PERSON_RX = re.compile(
    r"\b(?:i|we|i'?ll|we'?ll|i'?m|we'?re|i'?ve|we'?ve|i'?d|we'?d|let'?s|my|our)\b",
    re.IGNORECASE)
_BIND_BEFORE = 60
_BIND_AFTER = 40


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
    the start of the line (an imperative plan bullet, same convention as commitments.py)."""
    prefix = text[line_start:verb_start]
    if not prefix.strip():
        return True                                   # line-initial verb -> imperative
    return bool(_FIRST_PERSON_RX.search(prefix[-_BIND_BEFORE:]))


def source_plan_item_promise(text: str) -> Optional[dict]:
    """First plan/task label that is the object of a first-person, active, non-past, non-negated,
    non-conditional FORWARD promise, else None. Mirrors `commitments.py::_promise_location`'s
    clause discipline scoped to this label-shaped surface (not yet corpus-measured for FPs --
    named honestly in the module docstring)."""
    if not text:
        return None
    for m in _LABEL_RX.finditer(text):
        a, b = m.span()
        line_start = text.rfind("\n", 0, a) + 1
        before = text[max(0, a - _BIND_BEFORE):a]
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
        if not _first_person_governs(text, a - (len(before) - vm.start()), line_start):
            continue
        label = _normalize_label(m.group(1))
        desc = text[line_start:text.find("\n", b) if text.find("\n", b) != -1 else len(text)].strip()
        return {"label": label, "description": desc[:200]}
    return None


def source_plan_item_completions(text: str) -> set:
    """Labels this turn's text marks COMPLETE via a first-person past-tense verb governing them,
    or explicitly RETRACTS via a negation frame -- {(label, 'done'|'retracted'), ...}."""
    if not text:
        return set()
    out = set()
    for m in _LABEL_RX.finditer(text):
        a, b = m.span()
        before = text[max(0, a - _BIND_BEFORE):a]
        after = text[b:b + _BIND_AFTER]
        label = _normalize_label(m.group(1))
        if _NEGATED_RX.search(before) or _NEGATED_RX.search(after):
            out.add((label, "retracted"))
        elif _PAST_VERB_RX.search(before) or _PAST_VERB_RX.search(after):
            out.add((label, "done"))
    return out


def commitment_key(session_id: str, label: str) -> str:
    raw = f"{session_id}\x00{label}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


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
    calls, read off the PostToolUse payload (Task #19c, 2026-07-10). Unlike the prose sourcer
    above (regex over chat text, hardened but fuzzy by nature), a Task tool call is an explicit,
    deliberate act with a stable id -- there is nothing to guess. Payload shapes were captured
    LIVE from Makoto's own events table (this exact dispatch wiring), not from docs:

      TaskCreate  PostToolUse: tool_response = {"task": {"id": "1", "subject": ...}}
      TaskUpdate  PostToolUse: tool_input  = {"taskId": "1", ...}
                               tool_response = {"success": true, "taskId": "1",
                                                "statusChange": {"from": ..., "to": ...}}

    The label is `task:<id>` -- the SAME canonical key `_normalize_label` gives a prose mention
    of "Task #<id>", so a chat promise and the real Task object dedupe into one commitment. A
    `to: completed` transition discharges it ('done'); `to: deleted` retracts it; a create (or a
    resumed session's first update to a task this store never saw) opens it. Anything else --
    subject edits, ownership, blocks -- is not a lifecycle transition and is ignored. Fail-open:
    a malformed payload is a no-op, never a raise (callers additionally wrap, like every store)."""
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
            # a task this store never saw (resumed session) surfaces as open; an already-open
            # or retracted-then-resumed one re-opens -- record_plan_item's own upsert rule.
            record_plan_item(conn, session_id, {"label": label, "description": ""})
