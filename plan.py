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
from makoto.checks._planNode import Plan

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
    try:
        declare_plan(conn, session_id, raw)
    except ValueError:
        return None
    return load_plan(conn, session_id)
