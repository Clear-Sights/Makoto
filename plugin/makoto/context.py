"""makoto.context — the Stop-edge evaluation context (Stage 2 seam 4, final cut): the
`GateContext` schema (formerly `substrate/_shared.py`, ex-`stopchecks/_types.py`), the
`_history_for_agent` thread-boundary firewall, and `run_stop_checks` — the function that
assembles the Stop substrate (commitment sourcing -> retraction reconcile -> THEN read
open_commitments -> touched/empty keys -> fs closures) and evaluates every discovered Stop
check over it. Moved VERBATIM out of `dispatch.py`/`_shared.py`: the internal statement
order of `run_stop_checks` is behavior-bearing for gate.advance (validated 0-FP against the
1,335-session honest corpus) and must never be reordered "for clarity".

Knight-Leveson: stdlib only. NO LLM, NO HTTP. Called from `makoto.dispatch` (which re-imports
`run_stop_checks` under its own name for its Stop/SubagentStop handlers and for every existing
`from makoto.dispatch import run_stop_checks` consumer).
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from makoto.kit import decode_history_row
from makoto.registry import load_checks
from makoto.substrate._planNode import Plan


# ---- schemas (formerly stopchecks/_types.py) --------------------------------------------------
@dataclass(frozen=True)
class GateContext:
    """The Stop-event substrate, assembled ONCE per event and shared by every gate."""
    text: str
    touched: frozenset
    empty: frozenset
    opens: Sequence
    testrun_output: str
    cwd: str
    fs_exists: Callable
    fs_size: Callable
    fs_read: Callable
    history: Sequence = ()     # the events-table rows _select_recent returns (faithful: full
    #                            command + full tool_response per prior tool event). Fabrication
    #                            gates walk this like predicate content.unsourced_webfetch; default () keeps it optional.
    permission_mode: Optional[str] = None   # raw hook payload's `permission_mode` field verbatim
    #   (CONFIRMED real, snake_case, top-level on every hook event — Claude Code hooks reference,
    #   fetched 2026-07-06: "default"|"plan"|"acceptEdits"|"auto"|"dontAsk"|"bypassPermissions").
    #   No gate reads this yet (additive/observability-only per this ticket's scope).
    agent_id: Optional[str] = None          # raw `agent_id` — present only when the hook fired
    #   inside a subagent call (CONFIRMED real, top-level, per the same hooks reference). The
    #   nearest real substrate to a "this is a subagent" flag; no literal isSubAgent/isSidechain
    #   field exists in the documented schema, so this is the grounded substitute, not a guess.
    agent_type: Optional[str] = None        # raw `agent_type` (e.g. "Explore") — companion to
    #   agent_id, present when the session uses --agent or the hook fires inside a subagent.
    plan: Optional[Plan] = None             # the declared contract Plan (SPEC-5) for this
    #   session, loaded once by run_stop_checks via makoto.state.plan.load_plan; None when no plan is
    #   declared. Read by contractOrder's Stop GATE and staleEstablisher's advisory check.
    session_id: Optional[str] = None        # raw hook payload's `session_id` (Task 2 slice 5).
    transcript_path: Optional[str] = None   # raw `transcript_path` (CONFIRMED real, top-level on
    #   every hook event -- Claude Code hooks reference, fetched 2026-07-07: "Path to conversation
    #   JSONL file"). Read by canonFingerprints.py's release.operator discharge (makoto.state.ledger).
    state_root: Optional[object] = None     # the resolved state dir (Path), threaded through so
    #   the release.operator discharge can read/append the chain at the SAME root the dispatcher itself
    #   uses (never guessed via env-var fallback) -- same explicit-root discipline as audit.py.
    open_plan_items: Sequence = ()          # session/planItems.py's still-open label-shaped
    #   commitments ("§9.3", "Task #19"), synced once by run_stop_checks. Read by
    #   planItemDrift.py's ADVISORY-only reminder.
    history_all_agents: Sequence = ()       # the SAME _select_recent time-windowed slice as
    #   `history`, but NOT narrowed by _history_for_agent's thread-boundary firewall -- every
    #   agent's PostToolUse rows pooled. Exists for completed cross-agent evidence used by
    #   gate.claimed_running and gate.claimed_shipped: a subagent dispatched to start/verify a
    #   process or perform a remote mutation is real session evidence the main thread's own claim
    #   must see. `history` narrows to the calling
    #   thread specifically to stop a DANGLING (in-flight) PreToolUse from synthesizing a FAILURE
    #   across threads -- a risk that does not apply to a completed PostToolUse Bash call. Every
    #   other gate should keep reading `history`; widen a gate onto this field only with the same
    #   completed-evidence reasoning these claim gates document.

    @property
    def roots(self):
        return [self.cwd]

    @property
    def is_subagent(self) -> bool:
        """derived convenience: True iff this Stop substrate was built from a subagent-context
        payload (agent_id present) rather than the main agent."""
        return bool(self.agent_id)


def _history_for_agent(history, stop_payload: dict) -> list:
    """Return only history positively attributable to the thread ending in ``stop_payload``.

    Claude Code gives subagent hooks a non-empty top-level ``agent_id`` while the ordinary main
    loop is structurally a plain ``Stop`` with no ``agent_id`` key.  Preserve that distinction:
    exact-id subagents see exact-id rows, and a structurally plain main Stop sees only rows that
    are likewise structurally agentless.  An empty/malformed id, a SubagentStop with no id, or an
    undecodable row is ambiguous and contributes no history rather than entering a shared None
    bucket.  This intentionally fails open for an unidentifiable thread: pooling would let another
    agent's dangling PreToolUse synthesize failures and false-block every later Stop in a session.
    """
    if not isinstance(stop_payload, dict):
        return []
    if "agent_id" in stop_payload:
        agent_id = stop_payload.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id.strip():
            return []

        def belongs(payload):
            return payload.get("agent_id") == agent_id
    elif stop_payload.get("hook_event_name") == "Stop":
        def belongs(payload):
            return "agent_id" not in payload
    else:
        return []

    scoped = []
    for row in history or ():
        # The ONE canonical row-decode step (kit.decode_history_row), not a re-derived inline
        # copy: the two diverged on an empty-dict payload (inline kept it and let it count as
        # a structurally agentless row; the canonical decoder treats absent/empty as
        # undecodable -> the row contributes nothing, per this function's own ambiguity rule).
        payload = decode_history_row(row)
        if payload is not None and belongs(payload):
            scoped.append(row)
    return scoped


def run_stop_checks(conn, payload: dict, history=(), *, root=None) -> list:
    """Source + evaluate the completion / advance / green_claim gates for a Stop event.

    Reads the REAL `last_assistant_message` field; records any newly-stated located
    commitment (enter — records, never blocks); reads open commitments + the ledger's
    touched keys; re-derives the live filesystem. Returns a list of gate Findings
    (possibly empty). Fail-open at every step — a gate must never crash the hook or
    block on uncertainty. The caller decides whether these findings BLOCK (only when
    gates are explicitly enabled) or are audit-only (shadow mode for corpus FP mining).
    """
    try:
        # Thread-boundary firewall: no Stop gate may linearize another agent's events into this
        # agent's call stream. In particular, canon FD14-A must never synthesize a failure from a
        # dangling PreToolUse owned by a sibling subagent. Preserved BEFORE narrowing as
        # history_all_agents (below) -- gate.claimed_running's Bash-launch evidence deliberately
        # pools every thread, a completed PostToolUse row carrying none of the dangling-PreToolUse
        # risk this firewall exists to stop (see GateContext.history_all_agents).
        history_all_agents = history
        history = _history_for_agent(history, payload)
        # NO early return on empty text: five BLOCK gates (gate.canon, gate.contract_order,
        # gate.hollow_test, gate.liveness, gate.run_promised) never read `text` and must still
        # evaluate — skipping the whole catalog because `last_assistant_message` is absent made
        # absence read as green. Text-reading gates see "" and are naturally silent (no claim,
        # no finding), so this widens nothing for them.
        text = payload.get("last_assistant_message") or ""
        sid = payload.get("session_id", "")
        cwd = payload.get("cwd") or os.getcwd()
        from makoto.state import commitments as _C
        from makoto.state import ledger as _ledger
        from makoto.checks import normalize_path
        from makoto.state.commitments import surfaced_retraction_locations
        commit = _C.source_commitment(text)
        if commit:
            try:
                _C.record_commitment(conn, sid, commit, created_event_id=None)
            except Exception:
                pass
        # Reconcile: clear any open commitment the assistant EXPLICITLY + reason-bound retracts
        # (status='retracted') so the advance gate does not false-fire on a legitimately-dropped
        # promise. Firewall: NORMALIZED-EQUALITY membership only (retracting cache.py never
        # clears auth.py). Fail-open — a detector error must not crash the hook or mass-clear.
        try:
            retracted = surfaced_retraction_locations(text)
            if retracted:
                for c in _C.open_commitments(conn, sid):
                    if normalize_path(c["location"]) in retracted:
                        _C.set_status(conn, c["commitment_key"], "retracted",
                                      retract_param="surfaced-reason")
        except Exception:
            pass
        opens = _C.open_commitments(conn, sid)
        touched = _ledger.touched_keys(conn, sid)
        empty = _ledger.empty_write_keys(conn, sid)          # §7.1 content-depth signal
        from makoto.state import plan as _plan
        try:
            plan = _plan.load_plan(conn, sid)                # SPEC-5: the declared contract Plan
        except Exception:
            plan = None                                      # fail-open per-store, like every other read above
        try:
            _plan.sync_plan_items(conn, sid, text)           # source/discharge label-shaped commitments
            open_plan_items = _plan.open_plan_items(conn, sid)
        except Exception:
            open_plan_items = []                             # fail-open per-store, like every other read above

        # cwd-first, and on a miss resolve against git work-trees this session synced
        # (checks/_worldpaths.py) — a file produced remotely over ssh and landed here via
        # `git pull` is on disk under a repo root, not under cwd, and a bare-name claim
        # ("index.md") false-blocked gate.completion (issue #2). Observation widens; the
        # verdict doesn't: every alternate path still ends in a live os.path.exists.
        _wp_roots = None          # lazily resolved once per event, then reused (incl. empty)
        _wp_cache = {}

        def _world_path(p):
            nonlocal _wp_roots
            if p in _wp_cache:
                return _wp_cache[p]
            full = os.path.join(cwd, p)
            try:
                if not os.path.exists(full):
                    if _wp_roots is None:
                        from makoto.checks._worldpaths import synced_repo_roots
                        # UNNARROWED history, deliberately: a `git pull|fetch` is a COMPLETED
                        # PostToolUse Bash row, so it carries none of the dangling-PreToolUse
                        # risk the thread firewall exists to stop (the same completed-evidence
                        # reasoning gate.claimed_running/_shipped document for
                        # history_all_agents). Narrowed history made a SUBAGENT's sync
                        # invisible here, and gate.completion DENIED a true claim about a file
                        # that pull had landed on disk.
                        _wp_roots = synced_repo_roots(history_all_agents, cwd)
                    if _wp_roots:
                        from makoto.checks._worldpaths import resolve_in_synced_repos
                        alt = resolve_in_synced_repos(p, _wp_roots)
                        if alt:
                            full = alt
            except Exception:
                pass                                     # resolution failure -> original verdict
            _wp_cache[p] = full
            return full

        def fs_exists(p):
            try:
                return os.path.exists(_world_path(p))
            except Exception:
                return False

        def fs_size(p):
            try:
                full = _world_path(p)
                return os.path.getsize(full) if os.path.isfile(full) else None
            except Exception:
                return None

        def fs_read(p):
            try:
                full = _world_path(p)
                if os.path.isfile(full):
                    with open(full, encoding="utf-8", errors="replace") as fh:
                        return fh.read()
            except Exception:
                pass
            return None

        # Build the Stop substrate ONCE, then evaluate every live CHECK discovered for the Stop
        # edge (2026-07-10: unified via checks._loader.load_checks, retiring the former
        # load_stopchecks()-only loop -- this ALSO now naturally includes staleEstablisher and
        # undeclaredFalsifiable, formerly special-cased direct-call/never-invoked carve-outs below
        # this comment, since neither exported a GATE and load_stopchecks() never discovered them;
        # `may_block=False` on both keeps their pattern_id structurally out of
        # `_blocking_gate_ids()` regardless of this unification, exactly as before). Each gate
        # module owns its own adapter (GateContext -> the gate's heterogeneous signature), so this
        # loop never names a gate. gate.dropped resolves against the agent's OWN ledger
        # (touched_keys) + cwd-relative fs_exists/fs_read via ctx.roots=[cwd] — NOT an unbounded
        # os.walk (a Stop-hot-path landmine). meaning_gate / hidden_retraction were CUT (io-purge
        # B3): designs + measured FP evidence live in docs/MAKOTO-BIBLE.md; git history is the
        # recovery path.
        ctx = GateContext(
            text=text, touched=touched, empty=empty, opens=opens,
            testrun_output=_ledger.latest_testrun(conn, sid),
            cwd=cwd, fs_exists=fs_exists, fs_size=fs_size, fs_read=fs_read,
            history=history,   # faithful events-table rows (A1.3) — fabrication gates walk this
            history_all_agents=history_all_agents,   # unnarrowed twin — see GateContext's own doc
            # Additive decode-layer extension (observability-only, no gate reads these yet):
            # permission_mode/agent_id/agent_type are confirmed-real top-level hook payload
            # fields (Claude Code hooks reference) that dispatch.py never extracted before.
            permission_mode=payload.get("permission_mode"),
            agent_id=payload.get("agent_id"),
            agent_type=payload.get("agent_type"),
            plan=plan,   # SPEC-5: read by contractOrder's Stop GATE (below) + staleEstablisher (below)
            session_id=sid, transcript_path=payload.get("transcript_path"),
            state_root=root,   # Task 2 slice 5: canonFingerprints.py's release.operator discharge
            open_plan_items=open_plan_items,   # planItemDrift.py's ADVISORY-only reminder
        )
        out = []
        for check in sorted(load_checks(edge="Stop"), key=lambda c: c.id):
            try:
                finding = check.run(ctx)
            except Exception:
                continue   # fail-open PER CHECK: one check's fault must not suppress the others
            # CHECK.run -> Optional[Finding] | list[Finding]: most gates yield one finding, but
            # gate.liveness yields a list (a closed unit can have many illusory statements).
            # Normalize: a list/tuple is extended, a single finding appended, None ignored.
            if finding is None:
                continue
            if isinstance(finding, (list, tuple)):
                out.extend(finding)
            else:
                out.append(finding)
        return out
    except Exception:
        return []   # fail-open: gates never crash the hook
