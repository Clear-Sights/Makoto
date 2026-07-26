"""The EVENT surface matrix: a disposition for EVERY hook event the harness documents.

Mirrors Detent's detent/events.py exactly in shape, on the same rationale: "did you even look at
all the hooks?" must be structurally impossible to ask twice. Every event is WIRED (a real
handler is attached, and hooks/hooks.json must wire it — reconciled by test), HOLE (named,
honestly unbuilt or built-but-unshipped, with the unblock path), or OUT (declared outside
Makoto's writ, with the reason). Silence is not a state here either: tests/test_events.py pins
the full documented event list, so a harness release adding an event turns this matrix
stale-and-red, never silently incomplete.

Makoto's writ, unlike Detent's byte-flow domain, is narrower: it checks the ASSISTANT's own
claims against the assistant's own logged record (last_assistant_message, the ledger, the plan).
An event with no assistant claim in it has nothing for Makoto to verify — that is the OUT
boundary applied throughout below, distinct from Detent's byte-flow boundary.
"""
from __future__ import annotations

EVENTS: dict[str, dict] = {
    # ── WIRED — hooks/hooks.json wires exactly this set; each names its HANDLERS-table row ────
    # (_dispatch.py routing is the HANDLERS row table: adding an event is adding one row plus
    # at most one handler, never another branch in main().)
    "PreToolUse": {"status": "WIRED", "moves": (
        "_evaluate_and_gate", "_run_predicates", "_emit_decision")},
    "PostToolUse": {"status": "WIRED", "moves": (
        "_accumulate", "_ledger.record_update", "compute_delta",
        "_plan_items.record_task_event", "_event_location", "_plan.persist_plan",
        "_plan.declare_from_live_write"), "reason": (
        "accumulation only, never a blocking decision — the ledger update, the declared-Plan "
        "advance (a Write/Edit/MultiEdit/NotebookEdit at an open node's `where` resolves + marks "
        "it DONE, 2026-07-23 -- previously dead: mark_done/persist_plan had zero live callers, so "
        "a declared plan could never close, see gate.contract_order's Stop remainder), the "
        "declared-Plan LIVE DECLARE (a locating call that writes the artifact path itself, "
        "`.claude/makoto-plan.jsonl`, mid-session, 2026-07-23 -- previously the ONLY admission "
        "path was an artifact already on disk BEFORE SessionStart; nothing let Claude declare or "
        "replace a plan mid-session at all), and the TaskCreate/TaskUpdate plan-item sync always "
        "run; the test-delta finding is the one ADVISE-tier exception, surfaced via "
        "_emit_decision")},
    "Stop": {"status": "WIRED", "moves": (
        "_evaluate_and_gate", "run_stop_checks", "_blocking_gate_ids", "_emit_decision")},
    "SessionStart": {"status": "WIRED", "moves": (
        "_admit_plan", "declare_from_session_artifact"), "reason": (
        "was a HOLE at this matrix's first draft: main() carried this branch (admits a declared "
        "Plan from the on-disk artifact) but hooks/hooks.json never wired the event, so the "
        "branch was dead code in the shipped plugin. Wired 2026-07-12 on direct owner "
        "instruction (rule-4 sign-off given in-session), closing the gap the matrix surfaced")},
    "SubagentStop": {"status": "WIRED", "moves": (
        "_evaluate_and_gate", "run_stop_checks", "_blocking_gate_ids", "_emit_decision"),
        "reason": (
        "was a HOLE at this matrix's first draft: run_stop_checks/_blocking_gate_ids already "
        "evaluated `hook_event in (\"Stop\", \"SubagentStop\")` — a subagent's own completion "
        "claim checked by the same gates as a main-thread Stop — but hooks/hooks.json never "
        "wired the event, so the branch was unreachable. Wired 2026-07-12 on direct owner "
        "instruction (rule-4 sign-off given in-session), closing the gap the matrix surfaced")},

    # ── HOLE — a Makoto-shaped handler exists (or is unit-tested) but isn't shipped-wired ──────
    "ConfigChange": {"status": "HOLE", "reason": (
        "built, owner-authorized (2026-07-08, per _dispatch_configchange.py's own docstring), "
        "and unit-tested against constructed payloads (makoto.verdict.configchange_verdict) — "
        "but wired only in an operator's own local, uncommitted .claude/settings.json for "
        "self-hosted dogfooding, never in this repo's shipped hooks/hooks.json or "
        ".claude-plugin manifest. A live-fire probe during that dogfooding session was recorded "
        "as inconclusive, not confirmed-working (docs/self-defense-asymmetry-followup.md). "
        "Unblock: ship the hooks.json entry once live delivery is actually confirmed, same "
        "rule-4 sign-off as the others")},
    "PostToolUseFailure": {"status": "HOLE", "reason": (
        "the odd one of this section's four HOLEs: the other three mean 'code exists but is not "
        "shipped-wired'; this one means no design has ever been evaluated in this repo at all "
        "(no doc, no code path) — flagged explicitly so it isn't mistaken for the built-but-"
        "unwired flavor. It is a plausible in-domain candidate: a tool call that itself errored "
        "right before a completion claim is exactly the kind of contradiction Makoto's "
        "claim-checking domain should care about. Unblock: an owner-authorized design pass — "
        "same rule-4 posture as ConfigChange before it was built")},

    # ── OUT — declared outside Makoto's writ, each with its reason ─────────────────────────────
    "UserPromptSubmit": {"status": "OUT", "reason": (
        "carries ORACLE-authored content (the human's own words); Makoto verifies the "
        "ASSISTANT's claims against its own logged record, not the human's prompts. A claim can "
        "certainly be indexed to what was asked ('I ran the tests you asked for' presumes a "
        "specific ask) — but that indexing is resolved by reading the prompt back out of the "
        "already-ingested events table at Stop-check time (_select_recent/history), not by a "
        "dedicated UserPromptSubmit handler; nothing is lost by staying OUT here")},
    "UserPromptExpansion": {"status": "OUT", "reason": (
        "slash-command expansion provenance, not an assistant claim — Makoto checks what the "
        "assistant said and did, not how a command was expanded")},
    "SubagentStart": {"status": "OUT", "reason": (
        "nothing to verify yet at spawn — a subagent has made no claims; its claims are checked "
        "at its own completion (SubagentStop, see HOLE above), not at start")},
    "FileChanged": {"status": "OUT", "reason": (
        "no claim to verify — external-writer byte capture is Detent's domain (see Detent's own "
        "events.py), not Makoto's")},
    "MessageDisplay": {"status": "OUT", "reason": (
        "display-only rendering; no assistant claim to check (Makoto reads "
        "last_assistant_message content and the ledger, never how a reply is rendered)")},
    "PostToolBatch": {"status": "OUT", "reason": (
        "per-call coverage is already total via the wired PreToolUse/PostToolUse rows; batch "
        "granularity adds no new claim to check")},
    "Notification": {"status": "OUT", "reason": "control-plane; no claim/commitment content"},
    "SessionEnd": {"status": "OUT", "reason": "control-plane exit metadata; no claim content"},
    "StopFailure": {"status": "OUT", "reason": (
        "API failure metadata, control-plane; no assistant claim to check")},
    "PreCompact": {"status": "OUT", "reason": (
        "cannot inject context by protocol, and carries no assistant claim of its own")},
    "PostCompact": {"status": "OUT", "reason": (
        "Makoto's plan/commitment continuity is already sourced at SessionStart directly from "
        "the on-disk plan artifact (declare_from_session_artifact), independent of whether a "
        "compaction happened — nothing in Makoto's design depends on the compaction moment "
        "specifically, unlike Detent's summary-capture, which does")},
    "PermissionRequest": {"status": "OUT", "reason": "permission-decision plane; no claim content"},
    "PermissionDenied": {"status": "OUT", "reason": "same writ boundary as PermissionRequest"},
    "Setup": {"status": "OUT", "reason": "init-time maintenance; not a claim surface"},
    "TeammateIdle": {"status": "OUT", "reason": "control-plane scheduling signal"},
    "TaskCreated": {"status": "OUT", "reason": (
        "already served via a different route: the wired PostToolUse row inspects "
        "tool_name in (TaskCreate, TaskUpdate) directly (planItems.record_task_event) and "
        "derives task lifecycle from those tool calls; a dedicated TaskCreated hook event would "
        "duplicate coverage Makoto already has. This treats the TaskCreate/TaskUpdate TOOL calls "
        "as the exhaustive source of task lifecycle — if the harness ever fires the TaskCreated/ "
        "TaskCompleted hook EVENTS independent of those tool calls (e.g. harness-internal task "
        "tracking with no corresponding tool call), this OUT disposition should be revisited "
        "against live docs, the same discipline Detent applied to ConfigChange's schema")},
    "TaskCompleted": {"status": "OUT", "reason": "same route as TaskCreated — already served"},
    "Elicitation": {"status": "OUT", "reason": (
        "interactive decision-plane (MCP forms); answering forms is judgment, not a checkable "
        "assistant claim")},
    "ElicitationResult": {"status": "OUT", "reason": "same as Elicitation"},
    "WorktreeCreate": {"status": "OUT", "reason": "workspace lifecycle control-plane"},
    "WorktreeRemove": {"status": "OUT", "reason": "workspace lifecycle control-plane"},
    "InstructionsLoaded": {"status": "OUT", "reason": (
        "instruction-file load event; carries no assistant claim")},
    "CwdChanged": {"status": "OUT", "reason": "control-plane; no claim content"},
}
