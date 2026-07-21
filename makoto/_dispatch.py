"""Python dispatcher hot path — Spec §5.5.

Pipeline:
  stdin -> parse JSON -> ensure DB exists (lazy init) -> connect (with retry)
  -> refresh citations -> INSERT event (lastrowid) -> SELECT recent slice
  -> keyword prefilter -> iterate candidate predicates -> fold worst outcome
  through the configured posture (makoto.verdict.posture) -> render via the per-edge
  wire table (makoto.verdict.wire) -> stdout JSON iff non-empty -> append audit row
  -> exit 0.

main() is the thin orchestrator. Each stage is a small helper:
  _ensure_db_initialized, _connect_with_retry, _ingest_event,
  _select_recent, _run_predicates, _emit_decision, _record_audit.

Knight-Leveson: stdlib only (sqlite3). NO LLM, NO HTTP. The validator hot
path's imports are deliberately narrow.
"""
from __future__ import annotations
import importlib
import json
import os
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

from makoto.core.schema import load_prechecks, PreCheck, Finding
from makoto.record.state import _state_dir
from makoto.session import citations
from makoto.record import audit
from makoto.verdict import posture, wire
from makoto.record.audit import AuditRow
from makoto.substrate import factories
from makoto.substrate._loader import load_checks
from makoto.substrate._shared import GateContext


_EVENT_MAP = {
    "PreToolUse":   "live.pre_tool_use",
    "Stop":         "live.stop",
    "SubagentStop": "live.subagent_stop",
}


def _state_dir_from_conn(conn) -> Optional[Path]:
    """The makoto_state dir, derived from a live sqlite connection's own db file (its parent) — so a
    suppressed-match record lands beside the db the dispatch is already using, in unit calls and live
    alike. None for conn=None or an in-memory db (nothing recorded)."""
    if conn is None:
        return None
    try:
        for _seq, name, file in conn.execute("PRAGMA database_list").fetchall():
            if name == "main" and file:
                return Path(file).parent
    except Exception:
        return None
    return None


def _record_exemption_sink(*, current_event: dict, conn, pattern_id: str, kind: str,
                           file: str, line: int, reason: str, snippet: str) -> None:
    """The audit-writing sink injected into the L1 factories: a makoto-allow marker that suppressed a
    CONFIRMED match leaves an on-the-record exemptions.jsonl row (claim C3). I/O lives HERE in the L3
    orchestrator, not in the L1 detector, so factories keeps its down-only import contract."""
    state_dir = _state_dir_from_conn(conn)
    if state_dir is None:
        return
    try:
        audit.append_exemption(
            state_dir, pattern_id=pattern_id, kind=kind, file=file, line=line,
            reason=reason, snippet=snippet,
            session_id=current_event.get("session_id", ""),
            tool_name=current_event.get("tool_name", ""))
    except Exception:
        pass  # observability must never break the gate path


# Inject the recorder at import: `python -m makoto._dispatch` imports this module before main(), so the
# live hot path always records suppressed matches; a bare unit import of a precheck does not, keeping
# pure detector calls side-effect-free (the pre-existing exempt-returns-None contract is untouched).
factories.set_exemption_sink(_record_exemption_sink)

# SQLite(WAL) lock retry budget — concurrent hook fires (parallel tool calls,
# multi-session) can collide on the single-writer lock. busy_timeout absorbs most
# of it; this short retry around connect is a second layer, then we fail open so a
# transient collision never blocks agent work.
_LOCK_RETRY_ATTEMPTS = 5
_LOCK_RETRY_BACKOFF_S = 0.02  # 20ms × 5 = ~100ms total worst case


_PARSE_FAILED = object()  # sentinel: stdin was not valid JSON at all (distinct from a valid JSON `null`)


def _parse_payload(raw: str) -> object:
    """Parse stdin JSON. Return the parsed value, or the _PARSE_FAILED sentinel if `raw` was not
    valid JSON — distinct from a valid JSON `null` (which returns None). main()'s HYBRID fail-mode
    treats an unparseable pipe (loud-allow) and a non-object payload (block) differently."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return _PARSE_FAILED


class _Unevaluable(Exception):
    """A dispatch-stage can't-evaluate condition, recorded as an on-the-record fact (never silent)."""


def _dispatch_fact(state_dir: Path, stage: str, reason: str, *, blocked: bool) -> None:
    """HYBRID fail-mode: record an on-the-record can't-evaluate fact + a guaranteed-loud stderr line.
    NEVER silent. `blocked` marks a tamper-block vs a loud-allow in the recorded fact. The stderr line
    is the loud floor; the audit-file write is best-effort (the fact-writer must never itself crash
    the hook)."""
    disposition = "BLOCK" if blocked else "loud-allow"
    print(f"makoto._dispatch: {disposition} [{stage}] {reason}", file=sys.stderr)
    try:
        audit.append_error(state_dir, event_id=None, pattern_id=f"dispatch.{stage}",
                           exc=_Unevaluable(f"{disposition}: {reason}"))
    except Exception:
        pass


def _self_verify_chain(state_dir: Path) -> None:
    """Task 2 slice 3 (owner: "Makoto should read its own ledger for verification -- its things
    literally depend on it"). Re-derives the chain's own tamper-evidence at every dispatch, the
    same every-event cadence Assay's kernel ran. OWNER DECISION (2026-07-07): advisory-first,
    block-after-soak -- this ships ADVISORY ONLY (an on-the-record dispatch fact + a stderr line,
    never a block) until real-session soak evidence earns the flip to block, itself a later,
    separately-certified change. A clean or absent/empty chain is vacuously silent (verify_chain's
    own contract). NEVER RAISES: a verification fault must not crash the hot path it protects."""
    try:
        from makoto.record import ledger as _ledger
        broken_at = _ledger.verify_chain()
    except Exception as exc:
        _dispatch_fact(state_dir, "chain_verify_error", f"{type(exc).__name__}: {exc}", blocked=False)
        return
    if broken_at is not None:
        _dispatch_fact(state_dir, "chain_tamper",
                       f"chain integrity broken at row index {broken_at}", blocked=False)


def _ensure_db_initialized(state_dir: Path, db_path: Path) -> bool:
    """create makoto.record.db on first call if absent. Return False on init failure (fail-open)."""
    if db_path.exists():
        return True
    from makoto.record import db as _db_module
    citations_path = Path(__file__).parent / "docs" / "CITATIONS.md"
    try:
        _db_module.init_db(state_dir, citations_path)
        return True
    except Exception as exc:
        print(f"makoto._dispatch: lazy init failed: {exc}", file=sys.stderr)
        return False


def _connect_with_retry(db_path: Path):
    """open a write connection to makoto.record.db; retry on lock contention, then fail open.

    SQLite in WAL mode allows concurrent readers and a single writer. When two
    `python -m makoto._dispatch` processes write concurrently, the loser raises
    sqlite3.OperationalError ("database is locked") once busy_timeout elapses. We
    connect in autocommit mode (so citations.refresh_if_stale's explicit BEGIN/COMMIT is
    honored), retry briefly on a lock, then return None and let the caller fail open.
    """
    import sqlite3
    last_exc: Optional[Exception] = None
    for attempt in range(_LOCK_RETRY_ATTEMPTS):
        try:
            conn = sqlite3.connect(str(db_path), isolation_level=None)
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA journal_mode=WAL")
            return conn
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if "lock" not in str(exc).lower():
                raise  # not a lock error — propagate
            if attempt < _LOCK_RETRY_ATTEMPTS - 1:
                time.sleep(_LOCK_RETRY_BACKOFF_S * (attempt + 1))
    print(f"makoto._dispatch: db locked, failing open ({last_exc})", file=sys.stderr)
    return None


# The events table is a TRANSIENT evidence buffer, not a durable log: the only production
# reader is _select_recent, which never looks back past a 1-hour same-session window. Anything
# older is dead weight. We keep a small multiple of that window and prune the rest on every
# ingest, which hard-bounds the table to ~one working window's worth of rows regardless of how
# many sessions accumulate — the DB cannot grow without limit. Durable cross-session state lives
# in ledger/commitments; the fire (blocking-event) log lives in audit.jsonl. Neither is touched.
_EVENT_RETENTION_HOURS_DEFAULT = 1.5   # just over the 1-hour _select_recent read window (must stay >= it)


def _event_retention_hours() -> float:
    """Rolling-window size in hours (MAKOTO_EVENT_RETENTION_HOURS, default 1.5). A non-positive or
    unparseable value falls back to the default — never disables pruning, since an unbounded
    events table is the failure mode we are preventing."""
    raw = os.environ.get("MAKOTO_EVENT_RETENTION_HOURS", "").strip()
    try:
        v = float(raw)
    except ValueError:        # raw is always str (env.get default "") — TypeError arm was dead
        return _EVENT_RETENTION_HOURS_DEFAULT
    return v if v > 0 else _EVENT_RETENTION_HOURS_DEFAULT


def _prune_old_events(conn) -> None:
    """Delete events outside the rolling working window. Best-effort housekeeping: a failure here
    must never break ingestion (the gate path), so we swallow exceptions — worst case the table is
    transiently larger, never an integrity loss."""
    try:
        conn.execute(
            "DELETE FROM events WHERE ts < strftime('%Y-%m-%dT%H:%M:%fZ','now', ?)",
            [f"-{_event_retention_hours()} hours"],
        )
    except Exception:
        pass


def _ingest_event(conn, payload: dict, payload_raw: str) -> int:
    """INSERT the live event into the events table; return the assigned id. Prunes the rolling
    window on every ingest so the table stays bounded to ~_event_retention_hours()."""
    sid = payload.get("session_id", "")
    hook_event_name = payload.get("hook_event_name", "")
    cwd = payload.get("cwd", os.getcwd())
    cur = conn.execute(
        "INSERT INTO events (ts, session_id, event_type, cwd, payload) "
        "VALUES (strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?, ?, ?)",
        [sid, hook_event_name, cwd, payload_raw]
    )
    event_id = cur.lastrowid
    _prune_old_events(conn)
    return event_id


def _select_recent(conn, session_id: str, event_id: int) -> list:
    """fetch the strictly-prior 1-hour slice of events for this session."""
    return conn.execute(
        "SELECT id, ts, event_type, cwd, payload "
        "FROM events WHERE session_id = ? "
        "AND ts >= strftime('%Y-%m-%dT%H:%M:%fZ','now','-1 hour') "
        "AND id < ? ORDER BY ts",
        [session_id, event_id]
    ).fetchall()


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
        if isinstance(row, (tuple, list)) and len(row) > 4:
            raw = row[4]
        elif hasattr(row, "get"):
            raw = row.get("payload")
        else:
            continue
        try:
            payload = raw if isinstance(raw, dict) else json.loads(raw)
        except Exception:
            continue
        if isinstance(payload, dict) and belongs(payload):
            scoped.append(row)
    return scoped


def _keyword_hit(pattern: PreCheck, raw_payload: str) -> bool:
    """True iff any of pattern.keywords is a substring of raw_payload."""
    if not pattern.keywords:
        return False
    return any(kw in raw_payload for kw in pattern.keywords)


def _disabled_pattern_ids() -> frozenset[str]:
    """parse MAKOTO_DISABLE_PATTERNS=<id>,<id>,... into a frozenset of pattern ids.

    Epoch reset (2026-07-10): ids are their canonical family.name forms only -- the legacy-id
    alias closure was retired with the alias table itself (operator state and configs predating
    the reset are archived or wiped, so nothing left resolves through old ids)."""
    raw = os.environ.get("MAKOTO_DISABLE_PATTERNS", "")
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def _gates_enabled() -> bool:
    """Both Stop gates — completion (UNFULFILLED: claimed X produced, X absent) and advance
    (SELF-CONTRADICTING: claimed UNIVERSAL completion over an undischarged commitment) — BLOCK
    live by default, governed by one switch. Each is validated FP-clean on the 1335-session
    honest corpus:
      - completion: production-claim binding drove worst-case FP 9.00% -> self-healing 2.42%,
        TP intact (6/6), contamination canary passing.
      - advance (flipped live 2026-06-01): 0 fires across all 1335 sessions after the
        proposal-menu / code-fence / optional-parenthetical sourcing guards — every residual
        FP traced to a never-built PROPOSAL the AI recommended, never a genuine commitment
        (each of which discharged when its file was touched); TP intact (an undischarged firm
        promise + universal-done still fires), the reason-bound retraction path clears
        legitimately-dropped promises so honest re-prioritization never false-blocks.
    MAKOTO_DISABLE_GATES=1 returns BOTH to shadow (still audited, no block) — the single escape
    valve if a real-session false-block ever surfaces."""
    return os.environ.get("MAKOTO_DISABLE_GATES", "").strip().lower() not in ("1", "true", "yes", "on")


@lru_cache(maxsize=1)
def _blocking_gate_ids() -> frozenset:
    """The Stop-gate finding ids eligible to reach `_emit_decision` at all (BLOCK or surfaced
    ADVISE) when gates are enabled -- misnamed by history (kept for callers/tests already using
    it), but NOT a hand-synced literal: DERIVED from `Check.may_block` via
    `checks._loader.load_checks(edge="Stop")` (2026-07-10, retiring the former
    `load_stopchecks()`/`GATE`-export mechanism). `may_block=True` marks exactly the checks that
    used to export a `GATE` -- every one of them reaches this pipeline regardless of its own
    `.level`/posture (the actual BLOCK-vs-ADVISE split happens inside `_emit_decision`/
    `_worst_finding`, keyed on each Finding's own `.level`, unchanged by this migration).
    `staleEstablisher`/`undeclaredFalsifiable` stay `may_block=False` ON PURPOSE: their
    pattern_id must never enter this set at all, a STRUCTURAL exclusion independent of whatever
    `.level` their own `run()` might ever compute -- the former GATE-export-presence mechanism
    provided the exact same guarantee; this preserves it under the unified loader rather than
    collapsing to a single posture-only signal.

    Lazy + memoized: the loader imports every checks/*.py module, and Pre/PostToolUse dispatches
    (the per-event hot path) never consult this set — as a module-level constant they paid that
    import cost on every event. Stop dispatches load the same modules via run_stop_checks
    anyway, so laziness changes no Stop behavior."""
    return frozenset(c.id for c in load_checks(edge="Stop") if c.may_block)


def _run_predicates(conn, payload: dict, history: list, event_id: int,
                    state_dir: Path, payload_raw: str) -> list[Finding]:
    """keyword-prefilter the catalog, invoke each candidate predicate, collect Findings.

    Respects MAKOTO_DISABLE_PATTERNS env var (comma-separated ids) so a noisy
    pattern can be muted per-session without editing patterns.toml.

    Predicate exceptions are captured to dispatch_errors.jsonl (audit.append_error)
    and skipped — they must never block agent work.
    """
    patterns = load_prechecks()
    disabled = _disabled_pattern_ids()
    candidates = [p for p in patterns
                  if p.predicate_module and p.id not in disabled
                  and _keyword_hit(p, payload_raw)]
    # Silent-disable -> on-record: when MAKOTO_DISABLE_PATTERNS mutes a pattern that WOULD have been
    # a candidate (its keyword hit THIS payload), record the suppression. Brings env-var pattern
    # muting to the same auditable footing the Stop gates already have (MAKOTO_DISABLE_GATES audits
    # its shadowing). Zero cost in the default case: `disabled` empty -> the comprehension is empty.
    if disabled:
        for p in patterns:
            if p.predicate_module and p.id in disabled and _keyword_hit(p, payload_raw):
                try:
                    audit.append_exemption(
                        state_dir, pattern_id=p.id, kind="disabled-pattern",
                        file=payload.get("tool_input", {}).get("file_path", "") if isinstance(payload.get("tool_input"), dict) else "",
                        line=0, reason="muted via MAKOTO_DISABLE_PATTERNS", snippet="",
                        session_id=payload.get("session_id", ""), tool_name=payload.get("tool_name", ""))
                except Exception:
                    pass  # observability must never break the gate path
    findings: list[Finding] = []
    for pattern in candidates:
        try:
            mod = importlib.import_module(pattern.predicate_module)
            finding = mod.predicate(
                current_event=payload,
                history=history,
                pattern=pattern,
                conn=conn,
            )
            if finding is not None:
                # Stamp provenance centrally: every finding carries the events.id it was
                # derived from, without threading event_id through each predicate. The
                # detector decides WHAT fired; the dispatcher records WHICH event it came
                # from — single source of the id, one place to keep correct.
                findings.append(replace(finding, source_event_id=event_id))
        except Exception as exc:
            audit.append_error(state_dir, event_id, pattern.id, exc)
            continue
    return findings


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
        # dangling PreToolUse owned by a sibling subagent.
        history = _history_for_agent(history, payload)
        text = payload.get("last_assistant_message") or ""
        if not text:
            return []
        sid = payload.get("session_id", "")
        cwd = payload.get("cwd") or os.getcwd()
        from makoto.session import commitments as _C
        from makoto.record import ledger as _ledger
        from makoto.checks import normalize_path
        from makoto.verdict.retraction import surfaced_retraction_locations
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
        retracted = set()
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
        from makoto.session import plan as _plan
        try:
            plan = _plan.load_plan(conn, sid)                # SPEC-5: the declared contract Plan
        except Exception:
            plan = None                                      # fail-open per-store, like every other read above

        # cwd-first, and on a miss resolve against git work-trees this session synced
        # (checks/_worldpaths.py) — a file produced remotely over ssh and landed here via
        # `git pull` is on disk under a repo root, not under cwd, and a bare-name claim
        # ("index.md") false-blocked gate.completion (issue #2). Observation widens; the
        # verdict doesn't: every alternate path still ends in a live os.path.exists.
        _wp = {"roots": None, "cache": {}}

        def _world_path(p):
            if p in _wp["cache"]:
                return _wp["cache"][p]
            full = os.path.join(cwd, p)
            try:
                if not os.path.exists(full):
                    if _wp["roots"] is None:
                        from makoto.checks._worldpaths import synced_repo_roots
                        _wp["roots"] = synced_repo_roots(history, cwd)
                    if _wp["roots"]:
                        from makoto.checks._worldpaths import resolve_in_synced_repos
                        alt = resolve_in_synced_repos(p, _wp["roots"])
                        if alt:
                            full = alt
            except Exception:
                pass                                     # resolution failure -> original verdict
            _wp["cache"][p] = full
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
                    return open(full, encoding="utf-8", errors="replace").read()
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
            # Additive decode-layer extension (observability-only, no gate reads these yet):
            # permission_mode/agent_id/agent_type are confirmed-real top-level hook payload
            # fields (Claude Code hooks reference) that _dispatch.py never extracted before.
            permission_mode=payload.get("permission_mode"),
            agent_id=payload.get("agent_id"),
            agent_type=payload.get("agent_type"),
            plan=plan,   # SPEC-5: read by contractOrder's Stop GATE (below) + staleEstablisher (below)
            session_id=sid, transcript_path=payload.get("transcript_path"),
            state_root=root,   # Task 2 slice 5: canonFingerprints.py's release.operator discharge
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


# JIT conventions delivery: the installed CLAUDE.md block carries only the 3-line law; each
# check's convention + the `makoto-allow` escape hatch arrive HERE, at the moment they bind.
# A pattern is listed iff its predicate IMPLEMENTS the marker exemption (the factory scaffolds
# check makoto_allowed centrally; 1.6/1.34 call it directly) — bound to source by
# tests/test_conventions_jit.py, so the hint can never offer a hatch the code does not honor
# (1.9/1.21/1.22 are event-shapes with no content line to annotate; content.self_mute_guard self-mute refuses the
# marker — the seal on the mint cannot be signed by the would-be forger; gate.* check claims
# against the ledger, where the only discharge is doing or honestly retracting the thing said).
_ALLOW_EXEMPT_IDS = frozenset({
    "content.verifier_predicate_weakened", "content.env_gated_audit", "content.integrity_suppression_flag", "content.deferred_checkbox_theater", "content.phantom_citation", "content.verifier_body_hollowed",
    "content.illusory_authorship_trailer", "content.illusory_interruption_claim"})
_CONVENTIONS_PATH = Path(__file__).resolve().parent / "docs" / "MAKOTO-CONVENTIONS.md"
_HATCH_LINE = ("Legitimate instance? Annotate it `makoto-allow: <reason>` on or near the line "
               "(any comment style) — an on-the-record, auditable rationale, never a disguise.")


def _jit_hint(finding: Finding) -> str:
    """the fire-time message: the check's own convention first, then (iff the check honors the
    marker) the escape hatch, then the pointer to the full conventions."""
    parts = [finding.retry_hint] if finding.retry_hint else []
    if finding.pattern_id in _ALLOW_EXEMPT_IDS:
        parts.append(_HATCH_LINE)
    parts.append(f"Conventions: {_CONVENTIONS_PATH}")
    return "\n".join(parts)


_OUTCOME_FOR_LEVEL = {"error": posture.BLOCK, "advisory": posture.ADVISE}
_OUTCOME_RANK = {posture.BLOCK: 3, posture.ASK: 2, posture.ADVISE: 1, posture.ALLOW: 0}
# The live Claude Code hook-event name -> the edge name wire.dispatch_posture expects. Only
# PreToolUse renames (to "Pre"); Stop/SubagentStop pass through unchanged (wire.py's Stop table
# serves both, keyed by the SAME edge string "Stop"/"SubagentStop" it also echoes as hook_name).
_HOOK_TO_EDGE = {"PreToolUse": "Pre", "PostToolUse": "Post", "Stop": "Stop",
                "SubagentStop": "SubagentStop"}
# "PostToolUse" was missing until Task 3's test-delta redirect became the first PostToolUse
# caller of _emit_decision -- previously latent (the .get(..., "Pre") fallback silently rendered
# the WRONG edge's wire shape, with hookEventName="PreToolUse" on a PostToolUse response, had
# anything ever called _emit_decision from the PostToolUse branch before now).


def _worst_finding(findings: list[Finding]) -> Optional[tuple[str, Finding]]:
    """Pick the worst-outcome finding — BLOCK > ASK > ADVISE > ALLOW, first one at that rank
    (matching `_build_decision`'s old `errors[0]` precedent when multiple BLOCK findings fire).
    A level this catalog never emits (anything but 'error'/'advisory') maps to ALLOW, per the
    posture-vocabulary's own fail-open rule for an unrecognized outcome."""
    best = None
    for f in findings:
        outcome = _OUTCOME_FOR_LEVEL.get(f.level, posture.ALLOW)
        if best is None or _OUTCOME_RANK[outcome] > _OUTCOME_RANK[best[0]]:
            best = (outcome, f)
    return best


def _emit_decision(findings: list[Finding], hook_event: str, stream=None,
                   permission_mode=None) -> None:
    """Fold the worst fired outcome through the configured MAKOTO_MODE posture (posture.py) and
    render it via wire.dispatch_posture's per-edge table, writing the body to stdout iff non-empty.

    This is the real posture pipeline (SPEC-5 Task 8), replacing the old single ad-hoc
    "decision":"block" shape that main() used identically for every edge. A BLOCK outcome carries
    the finding's message plus its JIT hint (convention text / makoto-allow hatch / conventions
    pointer — the same text `_build_decision` used to put in "retry_hint") as the Decision's
    `.detail`, so wire.py's per-edge renderer surfaces it in place of its constant reason text.
    An ADVISE/ASK outcome at an edge whose table has no entry for it (e.g. ADVISE at Stop/
    SubagentStop — everything but BLOCK renders `{}` there by wire.py's own design) — and no
    findings at all — both fall through to "write nothing", matching the old None-decision case.

    `permission_mode` (D6, additive): threaded into `posture.apply` so a session running
    bypassPermissions/dontAsk is clamped to STRICT regardless of the operator's configured
    MAKOTO_MODE — see `posture.is_oversight_clamped`'s own docstring for why.
    """
    worst = _worst_finding(findings)
    if worst is None:
        return
    outcome, finding = worst
    detail = finding.message
    if outcome == posture.BLOCK:
        hint = _jit_hint(finding)
        if hint:
            detail = f"{detail}\n{hint}"
    folded = posture.apply(posture.Decision(outcome, detail), posture.posture(),
                           permission_mode=permission_mode)
    body = wire.dispatch_posture(_HOOK_TO_EDGE.get(hook_event, "Pre"), folded, hook_event)
    if body:
        (stream or sys.stdout).write(json.dumps(body))


def _record_audit(state_dir: Path, findings: list[Finding], payload: dict) -> None:
    """append an audit row IFF at least one Finding was produced (only-fires policy, 1.0.2).

    Silent hook fires carry no forensic signal; recording them flooded logs to
    99%+ noise. Predicate-level errors are captured separately via append_error.
    """
    if not findings:
        return
    hook_event_name = payload.get("hook_event_name", "")
    permission_mode = payload.get("permission_mode")
    # D6: record the clamp -- never override softening SILENTLY. None (the common case) when
    # this event's permission_mode isn't one of the two reduced-oversight modes.
    oversight_clamp = None
    if posture.is_oversight_clamped(permission_mode):
        oversight_clamp = {"active": True, "configured_mode": posture.posture(),
                           "permission_mode": permission_mode}
    row = AuditRow(
        ts=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        event=_EVENT_MAP.get(hook_event_name, hook_event_name),
        hook_kind=hook_event_name,
        session_id=payload.get("session_id", ""),
        project_root=payload.get("cwd", os.getcwd()),
        pattern_fires=sorted({f.pattern_id for f in findings}),
        exit_code=(2 if any(f.level == "error" for f in findings) else 0),
        retry_hint_emitted=any(f.retry_hint for f in findings),
        findings=[asdict(f) for f in findings],
        tool_name=payload.get("tool_name", ""),
        oversight_clamp=oversight_clamp,
    )
    audit.append_row(state_dir, row)


def _admit_plan(conn, payload, payload_raw, event_id, state_dir) -> None:
    """SessionStart — SPEC-5 (Makoto absorbs Assay): admit a declared Plan from the on-disk
    artifact. SessionStart never blocks — it is an admission step, not a gate — so this always
    completes silently regardless of whether a plan was actually declared."""
    try:
        from makoto.session import plan as _plan
        _plan.declare_from_session_artifact(
            payload.get("cwd") or os.getcwd(),
            payload.get("session_id", ""),
            conn,
            source=payload.get("source", ""),
        )
    except Exception as exc:
        print(f"makoto._dispatch: plan declare failed (non-fatal): {exc}",
              file=sys.stderr)


def _accumulate(conn, payload, payload_raw, event_id, state_dir) -> None:
    """PostToolUse — accumulation: store the event (already done by _ingest_event
    upstream so history-walking predicates can see tool_results) and record
    the `update` ledger row (Write/Edit touch, Bash result; latest-wins).
    No predicate evaluation and no block — PostToolUse is for accumulation,
    never decision. (SPEC-5 Task 8: citations.capture() removed here — see
    makoto/citations.py; refresh_if_stale upstream and record_update below are
    separate call sites and stay.)"""
    try:
        from makoto.record import ledger as _ledger
        from makoto.substrate.io import bash_output_text, is_test_runner
        from makoto.substrate._testDelta import compute_delta
        sid = payload.get("session_id", "")
        delta_finding = None
        # Task 3, the domain correction (test-delta redirect): compute the delta vs the
        # PRIOR recorded testrun BEFORE record_update's upsert overwrites it -- the only
        # point where "prior" is still readable. ADVISE-tier (Post has no fire_level
        # invariant -- Pre's error-only rule doesn't apply here): a factual diff is always
        # safe to surface, never a toothless hedge, so no discrimination problem exists.
        if payload.get("tool_name") == "Bash":
            cmd = (payload.get("tool_input", {}) or {}).get("command", "") or ""
            if is_test_runner(cmd):
                prior_output = _ledger.latest_testrun(conn, sid)
                tr = payload.get("tool_response", {})
                new_output = bash_output_text(tr) if isinstance(tr, dict) else ""
                delta = compute_delta(prior_output, new_output)
                if delta:
                    delta_finding = Finding(
                        pattern_id="makoto.test_delta", file="", line=0, level="advisory",
                        message=f"Test delta vs the prior recorded run: {delta}",
                        retry_hint="")
        _ledger.record_update(conn, payload, event_id=event_id,
                              session_id=sid, root=state_dir)
        if delta_finding is not None:
            delta_finding = replace(delta_finding, source_event_id=event_id)
            _emit_decision([delta_finding], payload.get("hook_event_name", ""),
                           permission_mode=payload.get("permission_mode"))
            # Found while building the D9 demo corpus: without this, the delta redirect's
            # own finding was invisible to the audit trail and the chain -- contradicting
            # Task 2's "every dispatch audit row is chain-appended" invariant. The redirect
            # fired on the wire correctly; it just never left a record of having fired.
            _record_audit(state_dir, [delta_finding], payload)
    except Exception as exc:
        print(f"makoto._dispatch: ledger update failed (non-fatal): {exc}",
              file=sys.stderr)


def _evaluate_and_gate(conn, payload, payload_raw, event_id, state_dir) -> None:
    """PreToolUse / Stop / SubagentStop — and the wildcard law for any event without its own
    row: keyword-prefiltered predicates, plus the Stop gates where the event carries a
    completion claim. Gates evaluate on Stop AND SubagentStop (real last_assistant_message) —
    a SubagentStop payload carries the same shape (last_assistant_message, session_id, cwd,
    etc.) as a main-thread Stop, so a sub-agent's own completion claim is checked by the same
    gates. The three Stop gates — completion, advance, and green_claim — block live under the
    single _gates_enabled() switch (each validated FP-clean on the 1335-session corpus;
    green_claim measured POWERED with real Bash output reconstructed in cert.replay_stop).
    All gate fires are always recorded to the audit log, block or not, so any future
    real-session FP can still be mined."""
    hook_event = payload.get("hook_event_name", "")
    history = _select_recent(conn, payload.get("session_id", ""), event_id)
    findings = _run_predicates(conn, payload, history, event_id,
                                state_dir, payload_raw)
    gate_findings = []
    if hook_event in ("Stop", "SubagentStop"):
        # Stop-edge CHECK findings get the same central provenance stamp: the Stop/SubagentStop
        # event they were evaluated against.
        gate_findings = [replace(f, source_event_id=event_id)
                         for f in run_stop_checks(conn, payload, history, root=state_dir)]
    blocking = list(findings)
    if _gates_enabled():
        blocking += [gf for gf in gate_findings
                     if gf.pattern_id in _blocking_gate_ids()]
    _emit_decision(blocking, hook_event, permission_mode=payload.get("permission_mode"))
    _record_audit(state_dir, findings + gate_findings, payload)


# The table: hook_event_name -> the event's pipeline. This is the whole routing — adding an
# event is adding one row plus (at most) one handler above, never another branch in main()
# (the same "a capability is a row, never a module" discipline as Detent's MOVES). The
# lookup's default is _evaluate_and_gate, the wildcard law: an event with no specialist row
# is held to the predicate catalog, so a newly wired event can never silently bypass
# evaluation — exactly the fall-through main()'s old if/elif chain provided, now as data.
HANDLERS: dict[str, Any] = {
    "SessionStart": _admit_plan,
    "PostToolUse": _accumulate,
    "PreToolUse": _evaluate_and_gate,
    "Stop": _evaluate_and_gate,
    "SubagentStop": _evaluate_and_gate,
}


def main() -> int:
    """orchestrator — HYBRID fail-mode (never silent, never blind-open): a tamper-shaped payload
    fails CLOSED (block, exit 2 + reason); transient infra (unparseable pipe, DB init/lock failure,
    unexpected body fault) fails LOUD-ALLOW (exit 0 + stderr); every can't-evaluate writes an
    on-the-record audit fact. See docs/archive/specs/2026-06-03-dispatch-fail-loud-hybrid-design.md.
    Routing is HANDLERS, the row table above — main() knows the common prologue (parse, verify,
    ingest) and nothing about any event."""
    payload_raw = sys.stdin.read()
    state_dir = _state_dir()
    _self_verify_chain(state_dir)
    payload = _parse_payload(payload_raw)
    if payload is _PARSE_FAILED:
        # unparseable stdin = a transient/truncated pipe (a real envelope is always valid JSON) ->
        # loud-allow; never block agent work on a pipe glitch.
        _dispatch_fact(state_dir, "unparseable_payload", "stdin was not valid JSON", blocked=False)
        return 0
    if not isinstance(payload, dict):
        # valid JSON but not an object: a truncated pipe yields INVALID json, never valid-non-dict,
        # and Claude Code's envelope is always an object -> anomalous/tamper-shaped -> fail CLOSED.
        _dispatch_fact(state_dir, "non_object_payload",
                       f"payload was {type(payload).__name__}, not a JSON object", blocked=True)
        return 2
    db_path = state_dir / "makoto.record.db"
    if not _ensure_db_initialized(state_dir, db_path):
        _dispatch_fact(state_dir, "db_init_failed", "lazy DB init failed", blocked=False)
        return 0  # transient infra -> loud-allow
    conn = _connect_with_retry(db_path)
    if conn is None:
        _dispatch_fact(state_dir, "db_locked", "write lock not acquired within retry budget", blocked=False)
        return 0  # transient infra -> loud-allow
    try:
        citations.refresh_if_stale(conn)
        event_id = _ingest_event(conn, payload, payload_raw)
        hook_event = payload.get("hook_event_name", "")
        handler = HANDLERS.get(hook_event, _evaluate_and_gate)
        handler(conn, payload, payload_raw, event_id, state_dir)
    except Exception as exc:
        # an unexpected fault in evaluation must never crash the hook to a non-zero exit, and must
        # never be silent -> loud-allow + fact. (Exception, not BaseException: Ctrl-C propagates.)
        _dispatch_fact(state_dir, "exception", f"{type(exc).__name__}: {exc}", blocked=False)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
