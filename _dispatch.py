"""Python dispatcher hot path — Spec §5.5.

Pipeline:
  stdin -> parse JSON -> ensure DB exists (lazy init) -> connect (with retry)
  -> refresh citations -> INSERT event (lastrowid) -> SELECT recent slice
  -> keyword prefilter -> iterate candidate predicates -> build decision
  -> stdout JSON if any error-level finding -> append audit row -> exit 0.

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

from makoto.schema import load_prechecks, PreCheck, Finding
from makoto.state import _state_dir
from makoto import citations, audit
from makoto.audit import AuditRow
from makoto.lib import factories
from makoto.stopchecks import load_stopchecks, GateContext


_EVENT_MAP = {
    "PreToolUse": "live.pre_tool_use",
    "Stop":       "live.stop",
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


def _ensure_db_initialized(state_dir: Path, db_path: Path) -> bool:
    """create makoto.db on first call if absent. Return False on init failure (fail-open)."""
    if db_path.exists():
        return True
    from makoto import db as _db_module
    citations_path = Path(__file__).parent / "docs" / "CITATIONS.md"
    try:
        _db_module.init_db(state_dir, citations_path)
        return True
    except Exception as exc:
        print(f"makoto._dispatch: lazy init failed: {exc}", file=sys.stderr)
        return False


def _connect_with_retry(db_path: Path):
    """open a write connection to makoto.db; retry on lock contention, then fail open.

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


def _keyword_hit(pattern: PreCheck, raw_payload: str) -> bool:
    """True iff any of pattern.keywords is a substring of raw_payload."""
    if not pattern.keywords:
        return False
    return any(kw in raw_payload for kw in pattern.keywords)


def _disabled_pattern_ids() -> frozenset[str]:
    """parse MAKOTO_DISABLE_PATTERNS=1.3,1.6,... into a frozenset of pattern ids.

    Empty / unset env var -> empty set (no patterns disabled). Whitespace and
    blank entries are tolerated.
    """
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
    """The Stop-gate finding ids that BLOCK when gates are enabled. DERIVED from load_stopchecks(),
    not a hand-synced literal: discovered <=> live <=> blocking — there is no
    audit-only (shadow) tier, so every discovered gate is in this set by construction (adding a gate
    cannot create a silent shadow gate). The former check.quantity (§7.2) shadow gate was CUT
    2026-06-02 (warning-tier-elimination cert): a gate that cannot block FP-safely is an illusory
    word. Every makoto signal BLOCKS or does not exist.

    Lazy + memoized: the loader imports every stopcheck_*.py module, and Pre/PostToolUse
    dispatches (the per-event hot path) never consult this set — as a module-level constant they
    paid that import cost on every event. Stop dispatches load the same modules via
    run_stop_checks anyway, so laziness changes no Stop behavior."""
    return frozenset(c.id for c in load_stopchecks())


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


def run_stop_checks(conn, payload: dict, history=()) -> list:
    """Source + evaluate the completion / advance / green_claim gates for a Stop event.

    Reads the REAL `last_assistant_message` field; records any newly-stated located
    commitment (enter — records, never blocks); reads open commitments + the ledger's
    touched keys; re-derives the live filesystem. Returns a list of gate Findings
    (possibly empty). Fail-open at every step — a gate must never crash the hook or
    block on uncertainty. The caller decides whether these findings BLOCK (only when
    gates are explicitly enabled) or are audit-only (shadow mode for corpus FP mining).
    """
    try:
        text = payload.get("last_assistant_message") or ""
        if not text:
            return []
        sid = payload.get("session_id", "")
        cwd = payload.get("cwd") or os.getcwd()
        from makoto import commitments as _C
        from makoto import ledger as _ledger
        from makoto.checks import normalize_path
        from makoto.retraction import surfaced_retraction_locations
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

        def fs_exists(p):
            try:
                return os.path.exists(os.path.join(cwd, p))
            except Exception:
                return False

        def fs_size(p):
            try:
                full = os.path.join(cwd, p)
                return os.path.getsize(full) if os.path.isfile(full) else None
            except Exception:
                return None

        def fs_read(p):
            try:
                full = os.path.join(cwd, p)
                if os.path.isfile(full):
                    return open(full, encoding="utf-8", errors="replace").read()
            except Exception:
                pass
            return None

        # Build the Stop substrate ONCE, then evaluate every live gate discovered by load_stopchecks().
        # discovered <=> live <=> blocking — there is no shadow tier. Each gate module owns its own
        # adapter (GateContext -> the gate's heterogeneous signature), so this loop never names a
        # gate. gate.dropped resolves against the agent's OWN ledger (touched_keys) + cwd-relative
        # fs_exists/fs_read via ctx.roots=[cwd] — NOT an unbounded os.walk (a Stop-hot-path landmine).
        # meaning_gate / hidden_retraction were CUT (io-purge B3): designs + measured FP evidence
        # live in docs/MAKOTO-BIBLE.md; git history is the recovery path.
        ctx = GateContext(
            text=text, touched=touched, empty=empty, opens=opens,
            testrun_output=_ledger.latest_testrun(conn, sid),
            cwd=cwd, fs_exists=fs_exists, fs_size=fs_size, fs_read=fs_read,
            history=history,   # faithful events-table rows (A1.3) — fabrication gates walk this
        )
        out = []
        for check in load_stopchecks():
            try:
                finding = check.run(ctx)
            except Exception:
                continue   # fail-open PER CHECK: one check's fault must not suppress the others
            # StopCheck.run -> Optional[Finding] | list[Finding]: most gates yield one finding, but
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
# (1.9/1.21/1.22 are event-shapes with no content line to annotate; 1.23 self-mute refuses the
# marker — the seal on the mint cannot be signed by the would-be forger; gate.* check claims
# against the ledger, where the only discharge is doing or honestly retracting the thing said).
_ALLOW_EXEMPT_IDS = frozenset({
    "1.1", "1.2", "1.4", "1.5", "1.6", "1.26", "1.27", "1.28", "1.29", "1.30",
    "1.31", "1.32", "1.33", "1.34"})
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


def _build_decision(findings: list[Finding]) -> Optional[dict]:
    """emit block decision iff any error-level finding exists (v5 fix #25)."""
    errors = [f for f in findings if f.level == "error"]
    if not errors:
        return None
    return {
        "decision": "block",
        "reason": errors[0].message,
        "retry_hint": _jit_hint(errors[0]),
        "additional_findings": [asdict(f) for f in errors[1:]],
    }


def _emit_decision(findings: list[Finding], stream=None) -> None:
    """write the block-decision JSON to stdout if any error-level finding exists."""
    decision = _build_decision(findings)
    if decision is not None:
        (stream or sys.stdout).write(json.dumps(decision))


def _record_audit(state_dir: Path, findings: list[Finding], payload: dict) -> None:
    """append an audit row IFF at least one Finding was produced (only-fires policy, 1.0.2).

    Silent hook fires carry no forensic signal; recording them flooded logs to
    99%+ noise. Predicate-level errors are captured separately via append_error.
    """
    if not findings:
        return
    hook_event_name = payload.get("hook_event_name", "")
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
    )
    audit.append_row(state_dir, row)


def main() -> int:
    """orchestrator — HYBRID fail-mode (never silent, never blind-open): a tamper-shaped payload
    fails CLOSED (block, exit 2 + reason); transient infra (unparseable pipe, DB init/lock failure,
    unexpected body fault) fails LOUD-ALLOW (exit 0 + stderr); every can't-evaluate writes an
    on-the-record audit fact. See docs/archive/specs/2026-06-03-dispatch-fail-loud-hybrid-design.md."""
    payload_raw = sys.stdin.read()
    state_dir = _state_dir()
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
    db_path = state_dir / "makoto.db"
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
        if hook_event == "PostToolUse":
            # Accumulation branch: store the event (already done by _ingest_event
            # above so history-walking predicates can see tool_results), capture
            # citations for research-class tools, and record the `update` ledger row
            # (Write/Edit touch, Bash result; latest-wins). No predicate evaluation
            # and no block — PostToolUse is for accumulation, never decision.
            try:
                citations.capture(
                    conn,
                    payload.get("tool_name", ""),
                    payload.get("tool_response", ""),
                )
            except Exception as exc:
                print(f"makoto._dispatch: capture failed (non-fatal): {exc}",
                      file=sys.stderr)
            try:
                from makoto import ledger as _ledger
                _ledger.record_update(conn, payload, event_id=event_id,
                                      session_id=payload.get("session_id", ""))
            except Exception as exc:
                print(f"makoto._dispatch: ledger update failed (non-fatal): {exc}",
                      file=sys.stderr)
            return 0
        history = _select_recent(conn, payload.get("session_id", ""), event_id)
        findings = _run_predicates(conn, payload, history, event_id,
                                    state_dir, payload_raw)
        # Gates evaluate on Stop (real last_assistant_message). The three Stop gates — completion,
        # advance, and green_claim — block live under the single _gates_enabled() switch (each
        # validated FP-clean on the 1335-session corpus; green_claim measured POWERED with real
        # Bash output reconstructed in cert.replay_stop). All gate fires are always recorded to the
        # audit log, block or not, so any future real-session FP can still be mined.
        gate_findings = []
        if hook_event == "Stop":
            # StopCheck findings get the same central provenance stamp: the Stop event they
            # were evaluated against.
            gate_findings = [replace(f, source_event_id=event_id)
                             for f in run_stop_checks(conn, payload, history)]
        blocking = list(findings)
        if _gates_enabled():
            blocking += [gf for gf in gate_findings
                         if gf.pattern_id in _blocking_gate_ids()]
        _emit_decision(blocking)
        _record_audit(state_dir, findings + gate_findings, payload)
    except Exception as exc:
        # an unexpected fault in evaluation must never crash the hook to a non-zero exit, and must
        # never be silent -> loud-allow + fact. (Exception, not BaseException: Ctrl-C propagates.)
        _dispatch_fact(state_dir, "exception", f"{type(exc).__name__}: {exc}", blocked=False)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
