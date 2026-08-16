"""Plan store: persist/read a declared contract Plan (SPEC-5 Makoto-absorbs-Assay merge).

Ported BY SHAPE (rule 5 -- copy, never import) from `assay/assay/runtime/engine.py`'s
declare/_persist/load/declare_from_artifact quartet (engine.py:160-230, 729-758), re-homed
onto Makoto's own `plans` sqlite table (see db.py) instead of Assay's `kernel.ledger` JSONL
stream (Makoto has no JSONL-store analog -- `makoto/ledger.py` is a different, narrower
substrate: `touched`/`testrun`/`value` rows keyed by normalized path, not a Plan container).
LATEST-WINS on the WHOLE plan per session_id, mirroring Assay's semantics exactly: `declare_plan`
replaces the whole plan (falsifiability-gated -- a non-falsifiable node rejects the WHOLE
declare); `persist_plan` rewrites the whole plan after a node advances (e.g. mark_done), with
no falsifiability re-check (every node was already gated at declare time). Dropped from the
Assay original: the anchored-bucket clear + owning-session store -- Makoto has no anchored-
fact/binding concept for a Plan to interact with (that gap is tracked separately, DEFERRED.md's
SPEC-5 Task 6 entry), so there is nothing here to port for that part.

SessionStart artifact path: `<cwd>/.claude/makoto-plan.jsonl`. Chosen because Makoto has no
existing per-PROJECT (not per-session-state) declared-artifact convention to reuse --
`makoto/state.py` only resolves the GLOBAL `$MAKOTO_STATE_DIR`; `makoto/install.py` only wires
`~/.claude/settings.json` / `~/.claude/CLAUDE.md`, both global, never per-project. This mirrors
Assay's own `<cwd>/.assay/plan.jsonl` convention, swapping in Makoto's own `.claude/` project
directory (the same directory Makoto's control-plane files already live under, per
`checks/forbiddenLocation.py`'s self-guard) rather than inventing a new `.makoto/` segment
Makoto has never used anywhere else.

Stdlib only; no LLM, no HTTP.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from makoto.checks import normalize_path
from makoto.substrate._planNode import Plan

# SessionStart only declares from the artifact on a genuinely-new session (mirrors Assay's own
# STARTUP-gated `declare_from_artifact`) -- a resume/clear/compact must never re-declare.
STARTUP = "startup"
_PLAN_ARTIFACT = ".claude/makoto-plan.jsonl"


def _is_falsifiable(what: str, passthrough: str, where: str) -> bool:
    """A declaration is FALSIFIABLE iff it has a non-empty operation WHAT, a non-empty operand
    NAME (passthrough), and a WHERE that normalizes to a concrete locator. A vacuous
    declaration cannot be held to anything."""
    return bool(what and passthrough and normalize_path(where))


def _upsert(conn, session_id: str, plan: Plan) -> None:
    conn.execute(
        "INSERT INTO plans (session_id, rows, ts) "
        "VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now')) "
        "ON CONFLICT(session_id) DO UPDATE SET rows=excluded.rows, ts=excluded.ts",
        [session_id, json.dumps(plan.rows())],
    )
    conn.commit()


def declare_plan(conn, session_id: str, plan: Plan) -> None:
    """Declare a (new or remade) plan LATEST-WINS for `session_id`. FALSIFIABILITY GATE: every
    declared node MUST be falsifiable (concrete what + passthrough + where) or the WHOLE declare
    is REJECTED (`ValueError`) -- an unholdable commitment never enters the store."""
    normalized = Plan()
    for row in plan.rows():
        where = normalize_path(row["where"])
        if not _is_falsifiable(row["what"], row["passthrough"], where):
            raise ValueError(
                f"non-falsifiable declaration {row!r}: a declared node needs a concrete "
                f"what + passthrough + where to be held to anything"
            )
        normalized.add_node(
            row["what"], row["passthrough"], where,
            id=row.get("id", ""), status=row.get("status", "open"),
        )
    _upsert(conn, session_id, normalized)


def persist_plan(conn, session_id: str, plan: Plan) -> None:
    """Save a plan's advanced statuses without re-declaring it (no falsifiability re-check --
    used after a node advances, e.g. `mark_done`)."""
    _upsert(conn, session_id, plan)


def load_plan(conn, session_id: str) -> Optional[Plan]:
    """The persisted plan for `session_id`, or `None` when none is declared / the row is absent
    or malformed. Fail-open."""
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT rows FROM plans WHERE session_id = ?", [session_id]
        ).fetchone()
    except Exception:
        return None
    if not row or not row[0]:
        return None
    try:
        rows = json.loads(row[0])
    except (ValueError, TypeError):
        return None
    if not rows:
        return None
    return Plan.from_rows(rows)


def _read_artifact_plan(cwd: str) -> Optional[Plan]:
    """Read + parse `<cwd>/.claude/makoto-plan.jsonl` into an un-declared `Plan`, or `None` on
    any absence/malformation (fail-open). The shared core BOTH admission paths use --
    `declare_from_session_artifact` (SessionStart) and `declare_from_live_write` (a live
    mid-session tool call writing the artifact itself) -- so the read/parse contract lives in
    exactly one place."""
    artifact = os.path.join(cwd, _PLAN_ARTIFACT) if cwd else _PLAN_ARTIFACT
    try:
        with open(artifact, "r", encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, ValueError):
        return None
    try:
        raw = Plan.from_jsonl(text)
    except (ValueError, KeyError, TypeError):
        return None
    if not raw.rows():
        return None
    return raw


def declare_from_session_artifact(
    cwd: str, session_id: str, conn, *, source: str = ""
) -> Optional[Plan]:
    """SessionStart: admit the plan from `<cwd>/.claude/makoto-plan.jsonl` and INSTANTIATE it
    for `session_id`, declaring ONLY on a genuinely-new session (`source == STARTUP`).

    An absent / unreadable / malformed / empty artifact declares NOTHING (fail-open, returns
    `None`). A plan carrying a NON-FALSIFIABLE node is REJECTED whole (`declare_plan` raises;
    caught -> `None`, fail-closed on tamper, not on absence). Returns the declared `Plan` or
    `None`.
    """
    if source != STARTUP:
        return None
    raw = _read_artifact_plan(cwd)
    if raw is None:
        return None
    try:
        declare_plan(conn, session_id, raw)
    except ValueError:
        return None
    return load_plan(conn, session_id)


def declare_from_live_write(cwd: str, session_id: str, conn) -> Optional[Plan]:
    """Mid-session admission (2026-07-23): a locating tool call (Write/Edit/MultiEdit) touched
    the plan artifact itself -- re-read `<cwd>/.claude/makoto-plan.jsonl` and re-declare
    LATEST-WINS, the SAME falsifiability gate and whole-plan-replace semantics
    `declare_from_session_artifact` uses, just triggered by a live tool call instead of session
    boot. Before this existed, the ONLY way to populate a plan was a file already sitting on disk
    BEFORE SessionStart fired -- nothing let Claude declare (or replace) a plan mid-session at
    all. Called from `makoto/dispatch.py`'s PostToolUse handler (`_accumulate`); see
    `makoto/events.py`'s PostToolUse entry. Same fail-open contract: absent, unreadable,
    malformed, empty, or non-falsifiable content declares nothing and returns `None`.
    """
    raw = _read_artifact_plan(cwd)
    if raw is None:
        return None
    try:
        declare_plan(conn, session_id, raw)
    except ValueError:
        return None
    return load_plan(conn, session_id)


# =============================================================================================
# plan-item commitments (merged from session/planItems.py -- Stage 2 seam 1)
_PLAN_ITEMS_DOC = """Plan-item commitments store: source open PLAN/TASK-LABELED promises ("I'll finish §9.3",
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
import hashlib
import re

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
# _OFFER_COND_RX / _FIRST_PERSON_RX: L0 shared lexicon (makoto.vocab -- dedup: was a
# byte-identical local copy of the exact regexes commitments.py hoisted; this file's own comment
# already said it "mirrors commitments.py's hardened guards" without the dedup happening).
from makoto.vocab import _OFFER_COND_RX, _FIRST_PERSON_RX
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
