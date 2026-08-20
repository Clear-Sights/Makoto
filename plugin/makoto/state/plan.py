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

import hashlib
import json
import os
import re
import sys
from typing import Optional

from makoto.checks import normalize_path
from makoto.substrate._planNode import Plan
# _OFFER_COND_RX / _FIRST_PERSON_RX: L0 shared lexicon (makoto.vocab -- dedup: was a
# byte-identical local copy of the exact regexes commitments.py hoisted; the plan-item section
# below already said it "mirrors commitments.py's hardened guards" without the dedup happening).
from makoto.vocab import _OFFER_COND_RX, _FIRST_PERSON_RX

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
        status = row.get("status", "open")
        if status != "open":
            # A node born DONE (or any non-open status) at declare time is as unholdable as a
            # vacuous one: there is nothing left to hold anyone to, so admitting it would empty
            # the remainder without the work happening. Same whole-plan rejection as the
            # falsifiability gate -- fail-closed on tamper, not on absence.
            raise ValueError(
                f"non-falsifiable declaration {row!r}: a declared node must start 'open' "
                f"(got status {status!r}) -- work cannot be born already discharged"
            )
        node_id = row.get("id", "")
        if node_id == f"{row['what']}::{row['passthrough']}::{row['where']}":
            # The id was auto-derived from the RAW `where` (PlanNode.__post_init__); re-derive
            # it from the normalized `where` so the stored node's identity and its `where`
            # agree with the documented "<what>::<passthrough>::<where>" composite.
            node_id = ""
        normalized.add_node(
            row["what"], row["passthrough"], where,
            id=node_id, status=status,
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
    # Parse PER LINE, not whole-artifact: one typo on line 3 of a 5-node plan must not silently
    # discard the other 4 nodes (that made a malformed line indistinguishable from "no plan
    # declared" -- absence reading green at Stop). A bad line is skipped LOUDLY (stderr, the
    # same diagnostic channel configchange.py uses; never stdout, which carries the hook's one
    # JSON object) and the remaining well-formed rows are still admitted. A line that is valid
    # JSON but not an object (`[]`, `1`, `"x"`) is the same defect class, and previously escaped
    # the fail-open contract entirely as an AttributeError out of `Plan.from_rows`.
    rows = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            print(f"makoto: {artifact}:{lineno}: malformed JSON line skipped; "
                  f"the remaining plan lines are still admitted", file=sys.stderr)
            continue
        if not isinstance(row, dict):
            print(f"makoto: {artifact}:{lineno}: JSON line is not an object; skipped",
                  file=sys.stderr)
            continue
        rows.append(row)
    if not rows:
        return None
    try:
        raw = Plan.from_rows(rows)
    except (ValueError, KeyError, TypeError):
        return None
    if not raw.rows():
        return None
    return raw


def _admit_artifact_plan(cwd: str, session_id: str, conn) -> Optional[Plan]:
    """Read the artifact and declare it LATEST-WINS -- the shared tail BOTH admission paths run.
    Absent / unreadable / malformed / empty declares NOTHING (fail-open, `None`); a plan carrying
    a NON-FALSIFIABLE node is REJECTED whole (`declare_plan` raises; caught -> `None`, fail-closed
    on tamper, not on absence). Returns the declared `Plan` or `None`."""
    raw = _read_artifact_plan(cwd)
    if raw is None:
        return None
    try:
        declare_plan(conn, session_id, raw)
    except ValueError:
        return None
    return load_plan(conn, session_id)


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
    return _admit_artifact_plan(cwd, session_id, conn)


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
    return _admit_artifact_plan(cwd, session_id, conn)


# =============================================================================================
# plan-item commitments (merged from session/planItems.py -- Stage 2 seam 1)
# Plan-item commitments store: source open PLAN/TASK-LABELED promises ("I'll finish §9.3",
# "next I need to close out Task #19") from the assistant's own text, and read them back
# un-windowed by session.
#
# Distinct from `session/commitments.py` (which sources a promise to a FILE PATH and discharges
# it by checking the filesystem/touched-keys): a plan/task label ("§9.3", "Task #19") has no
# filesystem location at all, so discharge here is PURELY TEXTUAL -- a later first-person
# completion statement naming the same label, or an explicit retraction. This closes the gap a
# real session hit: a forward commitment phrased as a section/task reference, never a file path,
# was silently dropped and never appeared in ANY commitment store because `commitments.py`'s
# sourcer requires a file-shaped location and found none.
#
# Sourcing discipline mirrors `commitments.py`'s hardened guards (first-person, active, non-past,
# non-negated, non-conditional) at the same rigor tier, scoped down for this narrower label-shaped
# surface rather than re-deriving from a real-session FP corpus this module has not been measured
# against yet -- see the module docstring's own caveat below.
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
# ("- start §9.3", "1. finish §9.3"). Same convention as commitments.py's _LINE_INITIAL_RX.
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
    the start of its line after at most a bullet/number marker (an imperative plan bullet, same
    convention as commitments.py's _LINE_INITIAL_RX)."""
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
    non-conditional FORWARD promise, else None. Mirrors `commitments.py::_promise_location`'s
    clause discipline scoped to this label-shaped surface (not yet corpus-measured for FPs --
    named honestly in the module docstring)."""
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
            # or retracted-then-resumed one re-opens -- record_plan_item's own upsert rule --
            # and a COMPLETED-then-resumed one re-opens too: the harness says the task is live
            # again, so a 'done' row must not stay discharged (record_plan_item's upsert only
            # lifts 'retracted', hence the explicit status set after it).
            record_plan_item(conn, session_id, {"label": label, "description": ""})
            set_plan_item_status(conn, session_id, label, "open")
