"""Python dispatcher hot path — Spec §5.5.

Pipeline:
  stdin -> parse JSON -> ensure DB exists (lazy init) -> connect (with retry)
  -> refresh citations -> INSERT event (lastrowid) -> SELECT recent slice
  -> keyword prefilter -> iterate candidate predicates -> fold worst outcome
  through the configured posture (makoto.verdict's posture fold) -> render via the per-edge
  wire table (makoto.verdict's wire tables) -> stdout JSON iff non-empty -> append audit row
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

from makoto.core import hostdialect
from makoto.vocab import Finding
from makoto.state.store import _state_dir
from makoto.state import citations
from makoto.state import audit
from makoto import verdict
from makoto.state.audit import AuditRow
from makoto import kit as factories
from makoto.registry import load_checks, load_precheck_catalog
from makoto.context import GateContext, _history_for_agent, run_stop_checks


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


# Inject the recorder at import: `python -m makoto.dispatch` imports this module before main(), so the
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
    print(f"makoto.dispatch: {disposition} [{stage}] {reason}", file=sys.stderr)
    try:
        audit.append_error(state_dir, event_id=None, pattern_id=f"dispatch.{stage}",
                           exc=_Unevaluable(f"{disposition}: {reason}"))
    except Exception:
        pass


def _note_host_dialect(state_dir: Path, session_id, notes: dict, host_event) -> bool:
    """Record ONCE PER SESSION that this host's envelopes are being translated. Returns whether
    this call was the one that recorded it.

    A dialect translation must be visible -- a rename nobody can see is indistinguishable from a
    bug the next time one of these fields turns up missing. But it must not be visible once per
    tool call: `_dispatch_fact` writes a guaranteed stderr line, and a foreign host translates
    EVERY event, so a per-event fact would put a line on the user's terminal for the whole session
    and grow the error ledger without adding information after the first row. Once per session is
    the whole signal -- the dialect is a property of the host, not of the call.

    Best-effort by construction: an unwritable marker degrades to re-noting (noisy but correct),
    never to crashing the hot path or to suppressing the note."""
    try:
        marker_dir = state_dir / "host_dialect"
        marker_dir.mkdir(parents=True, exist_ok=True)
        key = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(session_id or "nosession"))[:96]
        marker = marker_dir / f"{key}.json"
        if marker.exists():
            return False
        marker.write_text(json.dumps({"notes": notes, "host_event": host_event}) + "\n",
                          encoding="utf-8")
    except Exception:
        pass
    _dispatch_fact(state_dir, "host_dialect",
                   f"normalized host spellings {notes!r} (first seen as event {host_event!r}); "
                   f"noted once for this session", blocked=False)
    return True


def _self_verify_chain(state_dir: Path) -> None:
    """Verify the ledger chain on every dispatch, advisory-only and never raising.

    See docs/adr/0001-advisory-first-ledger-self-verification.md for the rollout decision."""
    try:
        from makoto.state import ledger as _ledger
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
    from makoto.state import store as _db_module
    citations_path = Path(__file__).parent / "docs" / "CITATIONS.md"
    try:
        _db_module.init_db(state_dir, citations_path)
        return True
    except Exception as exc:
        print(f"makoto.dispatch: lazy init failed: {exc}", file=sys.stderr)
        return False


def _connect_with_retry(db_path: Path):
    """open a write connection to makoto.record.db; retry on lock contention, then fail open.

    SQLite in WAL mode allows concurrent readers and a single writer. When two
    `python -m makoto.dispatch` processes write concurrently, the loser raises
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
    print(f"makoto.dispatch: db locked, failing open ({last_exc})", file=sys.stderr)
    return None


# The events table is a bounded transient evidence buffer, not a durable log.
# See docs/adr/0002-bound-the-transient-events-buffer.md for the retention rationale.
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
        "AND id < ? ORDER BY id",
        [session_id, event_id]
    ).fetchall()



def _keyword_hit(pattern, raw_payload: str) -> bool:
    """True iff any of pattern.keywords is a substring of raw_payload."""
    if not pattern.keywords:
        return False
    return any(kw in raw_payload for kw in pattern.keywords)


def _disabled_pattern_ids() -> frozenset[str]:
    """Parse disabled canonical pattern ids; legacy aliases are not supported.

    See docs/adr/0008-retire-legacy-pattern-id-aliases.md for the epoch-reset decision."""
    raw = os.environ.get("MAKOTO_DISABLE_PATTERNS", "")
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def _gates_enabled() -> bool:
    """Return whether the corpus-validated Stop gates may block live.

    See docs/adr/0003-enable-stop-gates-after-corpus-validation.md for the evidence and escape valve."""
    return os.environ.get("MAKOTO_DISABLE_GATES", "").strip().lower() not in ("1", "true", "yes", "on")


@lru_cache(maxsize=1)
def _blocking_gate_ids() -> frozenset:
    """Derive and memoize the structurally blocking-eligible Stop-check ids.

    See docs/adr/0004-unify-check-discovery-with-structural-block-eligibility.md for the loader migration."""
    return frozenset(c.id for c in load_checks(edge="Stop") if c.may_block)


@lru_cache(maxsize=1)
def _meta_check_ids() -> frozenset:
    """The ids of every check declaring `layer="meta"` -- a check whose only possible trigger is
    tampering with Makoto's own audit/enforcement machinery. DERIVED from `Check.layer` via
    `load_checks()` across every edge -- never hand-synced, matching `_blocking_gate_ids()`'s own
    discipline, so a check tagged meta is picked up here automatically, not by memory."""
    return frozenset(
        c.id for edge in ("Pre", "Post", "Stop", "SubagentStop", "SessionStart")
        for c in load_checks(edge=edge) if getattr(c, "layer", "object") == "meta"
    )


def _finding_layer(outcome, finding, mode, permission_mode) -> str:
    """Returns "meta" only on the exact branch where verdict.apply's meta-BLOCK floor can bind
    (a raw BLOCK, from a meta-tagged check, under LOOSE/SILENT posture, not oversight-clamped) --
    so the default STRICT hot path never pays the `_meta_check_ids()` catalog-derivation cost."""
    if outcome != verdict.BLOCK or mode not in ("loose", "silent"):
        return "object"
    if verdict.is_oversight_clamped(permission_mode):
        return "object"
    if finding.pattern_id in _meta_check_ids():
        return "meta"
    return "object"


def _run_predicates(conn, payload: dict, history: list, event_id: int,
                    state_dir: Path, payload_raw: str) -> list[Finding]:
    """keyword-prefilter the catalog, invoke each candidate predicate, collect Findings.

    Respects MAKOTO_DISABLE_PATTERNS env var (comma-separated ids) so a noisy
    pattern can be muted per-session without editing patterns.toml.

    Predicate exceptions are captured to dispatch_errors.jsonl (audit.append_error)
    and skipped — they must never block agent work.
    """
    # The registry is the sole catalog; tests pin the Pre tier's BLOCK-only invariant.
    # See docs/adr/0004-unify-check-discovery-with-structural-block-eligibility.md.
    patterns = load_precheck_catalog()
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


_OUTCOME_FOR_LEVEL = {"error": verdict.BLOCK, "advisory": verdict.ADVISE}
_OUTCOME_RANK = {verdict.BLOCK: 3, verdict.ASK: 2, verdict.ADVISE: 1, verdict.ALLOW: 0}
# The live Claude Code hook-event name -> the edge name verdict.dispatch_posture expects. Only
# PreToolUse renames (to "Pre"); Stop/SubagentStop pass through unchanged (verdict's Stop wire table
# serves both, keyed by the SAME edge string "Stop"/"SubagentStop" it also echoes as hook_name).
_HOOK_TO_EDGE = {"PreToolUse": "Pre", "PostToolUse": "Post", "Stop": "Stop",
                "SubagentStop": "SubagentStop"}
# PostToolUse must have its own wire edge rather than falling back to Pre.
# See docs/adr/0009-render-decisions-with-per-edge-wire-tables.md for the latent-fallback history.


def _recheck_certificate_enabled() -> bool:
    """Opt-in (OFF by default, mirroring the MAKOTO_DISABLE_* switch parsing): when
    MAKOTO_RECHECK_CERTIFICATE=1, `_emit_decision` re-verifies its own folded verdict via
    `makoto.verdict.recheck_certificate` before writing it to the wire. A mismatch
    RAISES (recheck.py's deliberate not-fail-open rule) — which is why this is opt-in: with the
    flag unset, production hook behavior is provably unchanged (this predicate is the only new
    code on the hot path, and it cannot raise)."""
    return os.environ.get("MAKOTO_RECHECK_CERTIFICATE", "").strip().lower() in ("1", "true", "yes", "on")


def _worst_finding(findings: list[Finding]) -> Optional[tuple[str, Finding]]:
    """Pick the worst-outcome finding — BLOCK > ASK > ADVISE > ALLOW, first one at that rank
    (matching `_build_decision`'s old `errors[0]` precedent when multiple BLOCK findings fire).
    A level this catalog never emits (anything but 'error'/'advisory') maps to ALLOW, per the
    posture-vocabulary's own fail-open rule for an unrecognized outcome."""
    best = None
    for f in findings:
        outcome = _OUTCOME_FOR_LEVEL.get(f.level, verdict.ALLOW)
        if best is None or _OUTCOME_RANK[outcome] > _OUTCOME_RANK[best[0]]:
            best = (outcome, f)
    return best


def _emit_decision(findings: list[Finding], hook_event: str, stream=None,
                   permission_mode=None) -> None:
    """Fold the worst fired outcome through the configured MAKOTO_MODE posture (makoto.verdict) and
    render it via verdict.dispatch_posture's per-edge table, writing the body to stdout iff non-empty.

    This is the real posture pipeline (SPEC-5 Task 8), replacing the old single ad-hoc
    "decision":"block" shape that main() used identically for every edge. A BLOCK outcome carries
    the finding's message plus its JIT hint (convention text / makoto-allow hatch / conventions
    pointer — the same text `_build_decision` used to put in "retry_hint") as the Decision's
    `.detail`, so verdict's per-edge wire renderer surfaces it in place of its constant reason text.
    An ADVISE/ASK outcome at an edge whose table has no entry for it (e.g. ADVISE at Stop/
    SubagentStop — everything but BLOCK renders `{}` there by the wire tables' own design) — and no
    findings at all — both fall through to "write nothing", matching the old None-decision case.

    `permission_mode` (D6, additive): threaded into `verdict.apply` so a session running
    bypassPermissions/dontAsk is clamped to STRICT regardless of the operator's configured
    MAKOTO_MODE — see `verdict.is_oversight_clamped`'s own docstring for why.
    """
    worst = _worst_finding(findings)
    if worst is None:
        return
    outcome, finding = worst
    detail = finding.message
    if outcome == verdict.BLOCK:
        hint = _jit_hint(finding)
        if hint:
            detail = f"{detail}\n{hint}"
    mode = verdict.posture()
    folded = verdict.apply(verdict.Decision(outcome, detail), mode,
                           permission_mode=permission_mode,
                           layer=_finding_layer(outcome, finding, mode, permission_mode))
    if _recheck_certificate_enabled():
        # CONTENT law (opt-in): pure data assembly from locals already in scope — the raw
        # pre-fold inputs paired with the post-fold claim — rechecked BEFORE the wire write so
        # a fold mismatch never reaches stdout. recheck_certificate raises on mismatch by
        # design (see makoto.verdict's recheck section); that raise is unreachable unless
        # MAKOTO_RECHECK_CERTIFICATE is explicitly set.
        from makoto.verdict import VerdictCertificate, recheck_certificate
        recheck_certificate(VerdictCertificate(
            findings=tuple(findings),
            mode=mode,
            permission_mode=permission_mode,
            claimed_outcome=str(folded),
            claimed_detail=getattr(folded, "detail", ""),
        ))
    body = verdict.dispatch_posture(_HOOK_TO_EDGE.get(hook_event, "Pre"), folded, hook_event)
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
    if verdict.is_oversight_clamped(permission_mode):
        oversight_clamp = {"active": True, "configured_mode": verdict.posture(),
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
        from makoto.state import plan as _plan
        _plan.declare_from_session_artifact(
            payload.get("cwd") or os.getcwd(),
            payload.get("session_id", ""),
            conn,
            source=payload.get("source", ""),
        )
    except Exception as exc:
        print(f"makoto.dispatch: plan declare failed (non-fatal): {exc}",
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
        from makoto.state import ledger as _ledger
        from makoto.kit import bash_output_text, is_test_runner
        from makoto.kit import compute_delta
        from makoto.checks.contractOrder import _LOCATING_TOOLS, _event_location
        from makoto.kit import _path_components
        sid = payload.get("session_id", "")
        cwd = payload.get("cwd") or os.getcwd()
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
        # Live writes both declare and advance plans through contractOrder's shared resolution.
        # See docs/adr/0006-wire-live-plan-declaration-and-advancement.md for the stranded-plan history.
        if payload.get("tool_name") in _LOCATING_TOOLS:
            from makoto.state import plan as _plan
            loc = _event_location(payload.get("tool_name", ""), payload.get("tool_input") or {})
            if loc is not None:
                if _path_components(loc)[-2:] == [".claude", "makoto-plan.jsonl"]:
                    # DECLARE: a locating call wrote the artifact itself -- (re-)admit it live,
                    # LATEST-WINS, the same falsifiability gate declare_plan always enforces.
                    _plan.declare_from_live_write(cwd, sid, conn)
                else:
                    # ADVANCE: a locating call at an OPEN node's own `where` marks it DONE.
                    plan_obj = _plan.load_plan(conn, sid)
                    if plan_obj is not None:
                        nid = plan_obj.resolve(loc, payload.get("tool_name", ""))
                        if nid is not None and nid in plan_obj.open_nodes():
                            plan_obj.mark_done(nid)
                            _plan.persist_plan(conn, sid, plan_obj)
        # Harness task events are the ground truth for the plan-item store.
        # See docs/adr/0006-wire-live-plan-declaration-and-advancement.md for the source decision.
        if payload.get("tool_name") in ("TaskCreate", "TaskUpdate"):
            from makoto.state import plan as _plan_items
            _plan_items.record_task_event(conn, sid, payload)
        if delta_finding is not None:
            delta_finding = replace(delta_finding, source_event_id=event_id)
            _emit_decision([delta_finding], payload.get("hook_event_name", ""),
                           permission_mode=payload.get("permission_mode"))
            # Audit the delta finding as well as rendering it.
            # See docs/adr/0009-render-decisions-with-per-edge-wire-tables.md for the discovered gap.
            _record_audit(state_dir, [delta_finding], payload)
    except Exception as exc:
        print(f"makoto.dispatch: ledger update failed (non-fatal): {exc}",
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
    # Normalize known host dialects before routing or persistence.
    # See docs/adr/0007-normalize-host-dialects-at-the-dispatch-boundary.md for the boundary decision.
    host_event = payload.get("hook_event_name")
    payload, dialect_notes = hostdialect.normalize_payload(payload, HANDLERS)
    if dialect_notes:
        # Persist the normalized payload that was evaluated; preserve non-ASCII for keyword scans.
        # See docs/adr/0007-normalize-host-dialects-at-the-dispatch-boundary.md for why.
        payload_raw = json.dumps(payload, ensure_ascii=False)
        _note_host_dialect(state_dir, payload.get("session_id"), dialect_notes, host_event)
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
