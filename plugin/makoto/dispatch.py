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
import re
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from makoto.core import hostdialect
from makoto.core import wire
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
    "PreToolUse":          "live.pre_tool_use",
    "PostToolUseFailure":  "live.post_tool_use_failure",
    "Stop":                "live.stop",
    "SubagentStop":        "live.subagent_stop",
}


def _state_dir_from_conn(conn) -> Path | None:
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


# Recovering the ids from raw stdin when the envelope did not parse. Deliberately a flat scan of
# the top-level shape Claude Code actually emits and nothing cleverer: this runs precisely when the
# payload is NOT trustworthy JSON, so a real parser is not available and a greedy one would invent
# structure. A miss yields "" and the row says `id_source: ""` -- honest silence, never a guess
# presented as a reading.
# Left UNCOMPILED on purpose. These are consulted only when the envelope did not parse, which is
# rare, while `re.compile` here is paid by every hook subprocess that ever starts -- measured at
# 196us for the three of them, on a path the overwhelming majority of events never reach. `re`
# keeps its own cache, and this function runs at most once per process, so a plain `re.search` on
# the pattern string is both cheaper at import and one moving part fewer.
_RAW_ID_PATTERNS = {
    "session_id": r'"session_id"\s*:\s*"([^"\\]{1,128})"',
    "tool_name": r'"tool_name"\s*:\s*"([^"\\]{1,64})"',
    "hook_event_name": r'"hook_event_name"\s*:\s*"([^"\\]{1,64})"',
}


def _ids_from_raw(payload_raw: str) -> dict:
    """Best-effort {session_id, tool_name, hook_event} recovered from unparsed stdin text."""
    found = {}
    for field, pattern in _RAW_ID_PATTERNS.items():
        m = re.search(pattern, payload_raw or "")
        if m:
            found[field] = m.group(1)
    if not found:
        return {}
    return {"session_id": found.get("session_id", ""),
            "tool_name": found.get("tool_name", ""),
            "hook_event": found.get("hook_event_name", ""),
            "id_source": "raw-scan"}


def _ids_from_payload(payload) -> dict:
    """{session_id, tool_name, hook_event} read from a parsed envelope, or {} if there isn't one."""
    if not isinstance(payload, dict):
        return {}
    return {"session_id": str(payload.get("session_id") or ""),
            "tool_name": str(payload.get("tool_name") or ""),
            "hook_event": str(payload.get("hook_event_name") or ""),
            "id_source": "payload"}


def _dispatch_fact(state_dir: Path, stage: str, reason: str, *, blocked: bool,
                   ids: dict | None = None, disposition: str | None = None) -> None:
    """HYBRID fail-mode: record an on-the-record can't-evaluate fact + a guaranteed-loud stderr line.
    NEVER silent. `blocked` marks a tamper-block vs a loud-allow in the recorded fact. The stderr line
    is the loud floor; the audit-file write is best-effort (the fact-writer must never itself crash
    the hook).

    `ids` carries the session/tool attribution (see `audit.append_error`). Every caller supplies it
    -- from the parsed payload where there is one, from `_ids_from_raw` where there isn't. A
    can't-evaluate fact that cannot be tied to a session is a fact nobody can act on: the row exists
    to answer "was THIS session affected", and unattributed rows answer that with a shrug.

    `disposition` overrides the recorded label for the one case that is neither of the two original
    fates: a payload that was REPAIRED and then evaluated normally. Filing that under "loud-allow"
    would inflate exactly the count this work exists to drive to zero, and would tell a reader that
    checks were skipped when they ran."""
    disposition = disposition or ("BLOCK" if blocked else "loud-allow")
    try:
        print(f"makoto.dispatch: {disposition} [{stage}] {reason}", file=sys.stderr)
    except Exception:
        # The stderr line is the LOUD FLOOR, and a floor that can raise is not a floor. stderr can
        # be closed, full, a broken pipe, or -- the failure mode this very module exists to fight
        # -- pinned to an encoder that refuses a character inside `reason`. Any of those escaped
        # this function, and from the prologue callers escaped `main()` outright: the REPORT of a
        # fault became a second, unreported fault, and took the hook's exit code with it. Losing
        # the line is bad; losing the notice and the audit row behind it is worse, so both durable
        # records below run either way.
        pass
    if not blocked and stage in _NOTICE_STAGES:
        _notices.append(f"[{stage}] {reason}")
    try:
        audit.append_error(state_dir, event_id=None, pattern_id=f"dispatch.{stage}",
                           exc=_Unevaluable(f"{disposition}: {reason}"), **(ids or {}))
    except Exception:
        pass


# ---------------------------------------------------------------------------------------------
# THE LOUD IN "LOUD-ALLOW". A fail-open that nobody can see is a silent one.
#
# `_dispatch_fact`'s stderr line was the entire "loud" half of the contract, and stderr from a hook
# that exits 0 goes to the DEBUG LOG ONLY -- never the transcript, never the user, never the model.
# So a can't-evaluate looked identical, from every seat, to a clean pass: the pending call
# proceeded, no output appeared, and the one party who could have retried or reported it was the
# only party not told. Measured: 30 loud-allows in one day, on one machine, noticed by nobody until
# somebody went looking through the state directory for an unrelated reason.
#
# `systemMessage` is a universal hook-output field that IS surfaced to the user, on every event
# that can carry output. Using it keeps the fail direction exactly where it was -- open, never
# blocking, a broken gate must not wedge the session -- while removing the "silently".
# Gyroscope's own shim reached the same conclusion for the same reason; this is that precedent
# applied one layer in, to the faults that happen after carriage succeeds.
#
# Only faults that mean A CHECK DID NOT RUN produce a notice. A REPAIRED payload evaluated normally
# and says nothing; a chain-tamper advisory has its own audit row and is not about this call.
_NOTICE_STAGES = frozenset({"unparseable_payload", "db_init_failed", "db_locked", "exception",
                            "prologue_exception"})
_notices: list = []
_stdout_written = False
# Set when the decision write itself raised. Distinct from `_stdout_written`, which only says the
# wire was CLAIMED -- see `_emit_decision`.
_decision_write_failed = False


def _emit_notices() -> None:
    """Write the buffered can't-evaluate notices to stdout, iff no decision already claimed it.

    The wire carries exactly ONE JSON object. A decision always outranks a notice -- a deny the
    agent must obey matters more than a report about a check that did not run -- so this is a
    last-word emitter, and `_stdout_written` is the interlock that keeps it from ever appending a
    second object onto a real decision and corrupting the response.
    """
    # `_decision_write_failed` is the exception to the claim: the wire was claimed, but the
    # decision never landed on it, so there is nothing for a notice to corrupt and everything for
    # it to explain.
    if not _notices or (_stdout_written and not _decision_write_failed):
        return
    try:
        detail = "; ".join(_notices[:3])
        sys.stdout.write(json.dumps({"systemMessage": (
            f"makoto: {len(_notices)} check-evaluation fault(s) on this call -- {detail}. "
            f"The call was ALLOWED WITHOUT BEING CHECKED (fail-open). "
            f"See dispatch_errors.jsonl in the makoto state dir.")}))
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
                   f"noted once for this session", blocked=False, disposition="NOTE",
                   ids={"session_id": str(session_id or ""), "hook_event": str(host_event or ""),
                        "id_source": "payload"})
    return True


def _self_verify_chain(state_dir: Path, ids: dict | None = None) -> None:
    """Re-derive the chain's tamper evidence at every dispatch, advisory-only. A clean or
    absent/empty chain is silent. Never raises. See docs/adr/0005-chain-verification-rollout.md.

    `ids` is the caller's session/tool attribution, threaded through for the same reason every
    other fact carries it: a tamper report nobody can tie to a session is a report nobody can
    act on."""
    try:
        from makoto.state import ledger as _ledger
        broken_at = _ledger.verify_chain()
    except Exception as exc:
        _dispatch_fact(state_dir, "chain_verify_error", f"{type(exc).__name__}: {exc}",
                       blocked=False, ids=ids)
        return
    if broken_at is not None:
        _dispatch_fact(state_dir, "chain_tamper",
                       f"chain integrity broken at row index {broken_at}", blocked=False, ids=ids)


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
    last_exc: Exception | None = None
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
        "AND id < ? ORDER BY id",
        [session_id, event_id]
    ).fetchall()


def _keyword_hit(pattern, raw_payload: str) -> bool:
    """True iff any of pattern.keywords is a substring of raw_payload."""
    if not pattern.keywords:
        return False
    return any(kw in raw_payload for kw in pattern.keywords)


def _disabled_pattern_ids() -> frozenset[str]:
    """Parse MAKOTO_DISABLE_PATTERNS=<id>,<id>,... as canonical family.name ids.
    See docs/adr/0006-canonical-pattern-ids.md for the epoch-reset history."""
    raw = os.environ.get("MAKOTO_DISABLE_PATTERNS", "")
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def _gates_enabled() -> bool:
    """Whether Stop gates block live; MAKOTO_DISABLE_GATES=1 returns them to audited shadow.
    See docs/adr/0007-stop-gates-live-rollout.md for rollout evidence."""
    return os.environ.get("MAKOTO_DISABLE_GATES", "").strip().lower() not in ("1", "true", "yes", "on")


@lru_cache(maxsize=1)
def _blocking_gate_ids() -> frozenset:
    """Stop-check ids eligible to reach `_emit_decision`, derived from `Check.may_block`.
    Lazy and memoized to avoid catalog imports outside Stop dispatch. See
    docs/adr/0002-may-block-field.md for the structural-eligibility history."""
    return frozenset(c.id for c in load_checks(edge="Stop") if c.may_block)


def _run_predicates(conn, payload: dict, history: list, event_id: int,
                    state_dir: Path, payload_raw: str) -> list[Finding]:
    """keyword-prefilter the catalog, invoke each candidate predicate, collect Findings.

    Respects MAKOTO_DISABLE_PATTERNS env var (comma-separated ids) so a noisy
    pattern can be muted per-session without editing patterns.toml.

    Predicate exceptions are captured to dispatch_errors.jsonl (audit.append_error)
    and skipped — they must never block agent work.
    """
    # Source directly from the unified checks catalog. See docs/adr/0001-unified-check-discovery.md.
    disabled = _disabled_pattern_ids()
    # ONE pass, two buckets. The admission test (`has a predicate` AND `its keyword hit THIS
    # payload`) is what decides both lists, so it is written once: a second copy of it in a
    # separate loop is a copy that can drift, and the pair only means anything while the two
    # agree. `_keyword_hit` is a pure substring scan, so hoisting it above the `disabled`
    # membership test costs nothing and changes nothing.
    candidates, muted = [], []
    for p in load_precheck_catalog():
        if p.predicate_module and _keyword_hit(p, payload_raw):
            (muted if p.id in disabled else candidates).append(p)
    # Silent-disable -> on-record: when MAKOTO_DISABLE_PATTERNS mutes a pattern that WOULD have been
    # a candidate, record the suppression. Brings env-var pattern muting to the same auditable
    # footing the Stop gates already have (MAKOTO_DISABLE_GATES audits its shadowing). Written
    # BEFORE any predicate runs, as before, so the exemption rows precede the run's own rows.
    tool_input = payload.get("tool_input")
    for p in muted:
        try:
            audit.append_exemption(
                state_dir, pattern_id=p.id, kind="disabled-pattern",
                file=tool_input.get("file_path", "") if isinstance(tool_input, dict) else "",
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
            # Guarded, and the guard is load-bearing. This is the ERROR path of one predicate, and
            # an `append_error` that raised here escaped `_run_predicates` ENTIRELY: every pattern
            # after this one was abandoned unevaluated, and the unwind landed in `_dispatch`'s
            # catch-all, which records a loud-allow and returns 0. A later predicate that would
            # have DENIED simply never ran -- so a failure in the error LOGGER silently turned a
            # deny into an allow. Observability must never decide a verdict; when the ledger
            # cannot be written, the remaining checks still finish.
            try:
                audit.append_error(state_dir, event_id, pattern.id, exc,
                                   **_ids_from_payload(payload))
            except Exception:
                pass
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
# The live Claude Code hook-event name -> the edge name verdict.dispatch_posture expects.
# PreToolUse renames to Pre; both settled tool terminals share Post; Stop/SubagentStop pass
# through unchanged (verdict's Stop wire table serves both, keyed by the SAME edge string
# "Stop"/"SubagentStop" it also echoes as hook_name).
_HOOK_TO_EDGE = {"PreToolUse": "Pre", "PostToolUse": "Post",
                 "PostToolUseFailure": "Post", "Stop": "Stop",
                 "SubagentStop": "SubagentStop"}
# Both settled tool terminals use the Post wire edge; see
# docs/adr/0010-posttooluse-wire-edge.md for why Post has its own edge.


def _recheck_certificate_enabled() -> bool:
    """Whether MAKOTO_RECHECK_CERTIFICATE enables pre-wire verdict verification. A mismatch
    raises. See docs/adr/0011-opt-in-verdict-recheck.md for why this remains opt-in."""
    return os.environ.get("MAKOTO_RECHECK_CERTIFICATE", "").strip().lower() in ("1", "true", "yes", "on")


def _worst_finding(findings: list[Finding]) -> tuple[str, Finding] | None:
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


@lru_cache(maxsize=1)
def _meta_check_ids() -> frozenset:
    """The check ids tagged `layer=\"meta\"` in the catalog (see Check.layer's docstring in
    makoto/registry.py) -- DERIVED from `load_checks()` across every edge, never a hand-synced
    literal, same discipline as `_blocking_gate_ids()`. Lazy + memoized because the loader
    imports every checks/*.py module: `_finding_layer` below only calls this on the one branch
    where the answer can matter (a BLOCK under a softening posture), so the default STRICT hot
    path never pays the import."""
    return frozenset(c.id for c in load_checks() if c.layer == "meta")


def _finding_layer(outcome: str, finding: Finding, mode: str, permission_mode) -> str:
    """The `layer` to hand `verdict.apply` for the worst finding -- \"meta\" iff the finding came
    from a meta-layer check AND the fold is on the one branch where the meta floor can bind (a
    raw BLOCK under LOOSE/SILENT with no oversight clamp). Everywhere else it returns \"object\",
    which is fold-equivalent to the true layer by `apply`'s own rule (the floor only acts on
    exactly that branch) -- so the catalog import in `_meta_check_ids` is never paid on the
    default-STRICT hot path. Shared verbatim by `verdict.recheck_certificate` so the F4
    certificate reconstruction folds identically."""
    if (outcome == verdict.BLOCK
            and mode in (verdict.LOOSE, verdict.SILENT)
            and not verdict.is_oversight_clamped(permission_mode)
            and finding.pattern_id in _meta_check_ids()):
        return "meta"
    return "object"


def _emit_decision(findings: list[Finding], hook_event: str, stream=None,
                   permission_mode=None) -> None:
    """Fold the worst fired outcome through the configured MAKOTO_MODE posture (makoto.verdict) and
    render it via verdict.dispatch_posture's per-edge table, writing the body to stdout iff non-empty.

    A BLOCK outcome carries the finding's message plus its JIT hint as the Decision detail.
    An ADVISE/ASK outcome at an edge whose table has no entry for it (e.g. ADVISE at Stop/
    SubagentStop) and no findings both produce no output. See
    docs/adr/0012-posture-pipeline-migration.md for the migration history.

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
    # The fold itself is DECISION machinery: a raise out of `posture`/`_finding_layer`/`apply`
    # (e.g. a malformed host value, or `_meta_check_ids` -> `load_checks` failing on the
    # LOOSE/SILENT+BLOCK branch) used to unwind through this function into `_dispatch`'s
    # carriage handler, which records a fact and returns 0 — a fired BLOCK converted into a
    # clean exit-0 allow. This repo's rule is open on carriage, closed on decision: on a fold
    # fault, honor the check's RAW outcome unchanged (the STRICT rule — a fold can only soften,
    # so this never escalates a check that found nothing).
    try:
        mode = verdict.posture()
        folded = verdict.apply(verdict.Decision(outcome, detail), mode,
                               permission_mode=permission_mode,
                               layer=_finding_layer(outcome, finding, mode, permission_mode))
    except Exception as exc:
        mode = verdict.DEFAULT_POSTURE
        folded = verdict.Decision(
            outcome,
            f"{detail}\n[makoto: verdict fold failed and fails closed on the raw outcome: "
            f"{type(exc).__name__}: {exc}]",
        )
    if _recheck_certificate_enabled():
        # CONTENT law (opt-in): pure data assembly from locals already in scope — the raw
        # pre-fold inputs paired with the post-fold claim — rechecked BEFORE the wire write so
        # a fold mismatch never reaches stdout. recheck_certificate raises on mismatch by
        # design (see makoto.verdict's recheck section); that raise is unreachable unless
        # MAKOTO_RECHECK_CERTIFICATE is explicitly set.
        from makoto.verdict import VerdictCertificate, recheck_certificate
        try:
            recheck_certificate(VerdictCertificate(
                findings=tuple(findings),
                mode=mode,
                permission_mode=permission_mode,
                claimed_outcome=str(folded),
                claimed_detail=getattr(folded, "detail", ""),
            ))
        except Exception as exc:
            # CAUGHT, and the direction matters more than the catch. Letting the raise fly was the
            # whole defect: it unwound past this wire write into `_dispatch`'s carriage handler,
            # which records a fact and returns 0 -- so the one mechanism built to catch a corrupted
            # fold produced NO verdict at all and the call was allowed. Detecting tampering in the
            # verdict machinery and then failing OPEN on the detection is worse than not checking.
            # A fold mismatch is a DECISION fault, not a carriage fault, and this repo's rule is
            # open on carriage, closed on decision -- so the mismatch becomes the verdict, at BLOCK,
            # bypassing `apply` entirely (the fold is exactly what is not to be trusted here).
            folded = verdict.Decision(
                verdict.BLOCK,
                "makoto could not certify its own verdict fold and is failing closed: "
                f"{type(exc).__name__}: {exc}",
            )
    # Meta-floor teeth at the Stop edges: `apply` floors a meta BLOCK to ASK under a softening
    # posture, but `_STOP_WIRE` deliberately has no ASK entry ("ASK never blocks the agent from
    # stopping" — pinned by tests/test_posture_wire.py), so at Stop/SubagentStop that floored
    # ASK rendered {} — the tamper finding suppressed EXACTLY as the floor exists to prevent,
    # indistinguishable from ALLOW. Both components are pinned; the composition is corrected
    # here: a BLOCK from a meta-layer check that folded to ASK on a Stop-shaped edge renders as
    # the BLOCK body (STRICT's own rendering), after the certificate check so the recorded fold
    # stays coherent. Object-layer ASKs at Stop keep their pinned no-objection rendering.
    if (hook_event in ("Stop", "SubagentStop") and outcome == verdict.BLOCK
            and str(folded) == verdict.ASK):
        try:
            is_meta = finding.pattern_id in _meta_check_ids()
        except Exception:
            is_meta = True          # catalog unloadable: decision machinery -> fail closed
        if is_meta:
            folded = verdict.Decision(verdict.BLOCK, detail)
    edge = _HOOK_TO_EDGE.get(hook_event, "Pre")
    try:
        body = verdict.dispatch_posture(edge, folded, hook_event)
    except Exception as exc:
        # Same fail-closed rule as the fold above: a raise while RENDERING the verdict must not
        # become an exit-0 allow. Re-render what the fold already concluded with minimal
        # hand-built bodies — never escalating: anything that folded below BLOCK/ASK stays {}.
        reason = (f"makoto: {getattr(folded, 'detail', '') or detail} "
                  f"[wire render failed and fails closed: {type(exc).__name__}: {exc}]")
        if str(folded) == verdict.BLOCK and edge in ("Stop", "SubagentStop"):
            body = {"decision": "block", "reason": reason, "hookEventName": hook_event}
        elif str(folded) == verdict.BLOCK and edge == "Pre":
            body = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                           "permissionDecision": "deny",
                                           "permissionDecisionReason": reason}}
        elif str(folded) == verdict.ASK and edge == "Pre":
            body = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                           "permissionDecision": "ask",
                                           "permissionDecisionReason": reason}}
        else:
            body = {}
    if body:
        global _stdout_written, _decision_write_failed
        # Claim the wire BEFORE the write, not after. The claim is about having BEGUN to write,
        # not about having finished: a write that fails part-way -- a broken pipe, a full disk,
        # an encoder refusing a byte mid-buffer -- left the flag False with bytes already on
        # stdout, and `main`'s `finally` then appended a whole second JSON object onto the
        # fragment. Observed shape: `{"hookSpecif{"systemMessage": ...`, which no host can parse,
        # so a real DENY became an unreadable response. Claiming first degrades the same failure
        # to a truncated single object, which a host rejects as one bad message instead of
        # silently mis-reading two.
        # Set even for an injected `stream`: a caller that redirected the wire still owns it.
        _stdout_written = True
        try:
            (stream or sys.stdout).write(json.dumps(body))
        except Exception:
            # A stream that rejects the write OUTRIGHT -- EPIPE on the first byte, a closed fd --
            # leaves stdout empty, and the claim above would then suppress the notice as well:
            # the DENY reaches nobody, no notice reaches anybody, and the hook looks like a clean
            # pass. That is the loud-allow this plugin promises, gone silent. Recording the
            # failure lets `_emit_notices` speak in exactly that case. A half-written fragment is
            # already unparseable, so a notice behind it cannot turn a good response into a bad
            # one -- it can only add the one signal that says a check did not decide anything.
            _decision_write_failed = True
            raise


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
    """Settled-tool accumulation, with failure evidence kept out of success-shaped state.

    Both PostToolUse terminals have already been stored by ``_ingest_event`` before this handler
    runs, so history-walking decoders can see successes and failures alike.  Only a successful
    PostToolUse may mutate the update ledger, advance a plan, record a task event, or emit a test
    delta.  PostToolUseFailure is evidence that the operation did *not* land; retaining it in
    history while returning here prevents a failed Write/Bash from discharging gates or
    latest-wins clobbering an earlier real result.

    No predicate evaluation and no block — settled tool events accumulate evidence, never decide.
    See docs/adr/0013-posttooluse-accumulation.md for the migration history."""
    if payload.get("hook_event_name") == "PostToolUseFailure":
        return
    try:
        from makoto.state import ledger as _ledger
        from makoto.kit import (_path_components, bash_output_text, compute_delta,
                                is_test_runner)
        from makoto.checks.contractOrder import _LOCATING_TOOLS, _event_location
        sid = payload.get("session_id", "")
        cwd = payload.get("cwd") or os.getcwd()
        delta_finding = None
        # Compute test delta before record_update overwrites the prior run; surface it as ADVISE.
        # See docs/adr/0019-test-delta-domain-correction.md for why.
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
        # Locating tools declare or advance the live plan through the shared Plan.resolve contract.
        # See docs/adr/0014-live-plan-lifecycle.md for why.
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
        # TaskCreate/TaskUpdate are the plan-item store's ground truth; this remains fail-open.
        # See docs/adr/0015-plan-item-event-source.md for why.
        if payload.get("tool_name") in ("TaskCreate", "TaskUpdate"):
            from makoto.state import plan as _plan_items
            _plan_items.record_task_event(conn, sid, payload)
        if delta_finding is not None:
            delta_finding = replace(delta_finding, source_event_id=event_id)
            _emit_decision([delta_finding], payload.get("hook_event_name", ""),
                           permission_mode=payload.get("permission_mode"))
            # Persist the delta redirect finding; see docs/adr/0016-delta-finding-audit.md for why.
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
    gates. Stop gates block live under `_gates_enabled`; every fire is audited regardless.
    See docs/adr/0007-stop-gates-live-rollout.md for rollout evidence."""
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


# The table maps hook_event_name to its pipeline; unknown events use the evaluation pipeline.
# See docs/adr/0017-table-driven-event-routing.md for the design history.
HANDLERS: dict[str, Any] = {
    "SessionStart": _admit_plan,
    "PostToolUse": _accumulate,
    "PostToolUseFailure": _accumulate,
    "PreToolUse": _evaluate_and_gate,
    "Stop": _evaluate_and_gate,
    "SubagentStop": _evaluate_and_gate,
}


def main() -> int:
    """Run the dispatch and then GUARANTEE the can't-evaluate notices reach the wire.

    Every early `return 0` in `_dispatch` is a fail-open, and a fail-open is exactly the path whose
    notice must not be lost, so the flush is a `finally` rather than a line before each return --
    the same reason `_dispatch`'s own conn.close() is one.
    """
    # Reset FIRST. These are module globals, and a second `main()` in one interpreter inherited
    # the first call's buffered notices and its spent wire claim: the notices were re-reported
    # under the wrong event and grew without bound, while `_stdout_written` left over from a
    # previous decision suppressed this call's notice entirely. Production forks a process per
    # event and never noticed; every in-process caller -- the tests, and any host that batches --
    # did.
    global _stdout_written, _decision_write_failed
    _notices.clear()
    _stdout_written = False
    _decision_write_failed = False
    try:
        return _dispatch()
    except Exception as exc:
        # `_dispatch` wraps only the HANDLER in a catch-all, so its whole prologue -- the stdin
        # read, the state-dir resolve, the parse, the chain self-verify -- ran with no catch at
        # all, and a `finally` does not absorb, it re-raises. A fault in any of those left the
        # hook with a traceback and a non-zero exit instead of the loud-allow that IS this
        # plugin's declared fail direction for carriage faults. Same disposition as every other
        # carriage fault: recorded, loud, allowed. `_state_dir()` is resolved again here rather
        # than reused, because the fault may well be the one that stopped it resolving the first
        # time -- and if even that fails, the bare stderr line is still the floor.
        try:
            _dispatch_fact(_state_dir(), "prologue_exception", f"{type(exc).__name__}: {exc}",
                           blocked=False)
        except Exception:
            _notices.append(f"[prologue_exception] {type(exc).__name__}: {exc}")
            try:
                print(f"makoto.dispatch: loud-allow [prologue_exception] "
                      f"{type(exc).__name__}: {exc}", file=sys.stderr)
            except Exception:
                pass
        return 0
    finally:
        _emit_notices()


def _dispatch() -> int:
    """orchestrator — HYBRID fail-mode (never silent, never blind-open): a tamper-shaped payload
    fails CLOSED (block, exit 2 + reason); transient infra (unparseable pipe, DB init/lock failure,
    unexpected body fault) fails LOUD-ALLOW (exit 0 + stderr); every can't-evaluate writes an
    on-the-record audit fact. See docs/archive/specs/2026-06-03-dispatch-fail-loud-hybrid-design.md.
    Routing is HANDLERS, the row table above — main() knows the common prologue (parse, verify,
    ingest) and nothing about any event."""
    # The byte boundary comes FIRST, before anything reads a character. `makoto.core.wire` pins the
    # decode to errors="replace" instead of inheriting the ambient locale's surrogateescape handler,
    # so a host byte that is not valid UTF-8 can no longer enter as a lone surrogate and detonate
    # later, inside sqlite3, as the loud-allow that skipped every check for that call. See
    # makoto/core/wire.py for the measured failure this closes.
    wire.harden_stderr()
    payload_raw, undecodable = wire.read_stdin()
    state_dir = _state_dir()
    payload = _parse_payload(payload_raw)
    # Chain self-verification is advisory and session-scoped, but its two facts are rows in the
    # same log as everything else, so it runs AFTER the parse in order to be tagged with the ids
    # like every other row. Nothing it does depends on the payload; only its attribution does.
    _self_verify_chain(state_dir, ids=_ids_from_payload(payload) or _ids_from_raw(payload_raw))
    if payload is _PARSE_FAILED:
        # unparseable stdin = a transient/truncated pipe (a real envelope is always valid JSON) ->
        # loud-allow; never block agent work on a pipe glitch.
        _dispatch_fact(state_dir, "unparseable_payload", "stdin was not valid JSON", blocked=False,
                       ids=_ids_from_raw(payload_raw))
        return 0
    if not isinstance(payload, dict):
        # valid JSON but not an object: a truncated pipe yields INVALID json, never valid-non-dict,
        # and Claude Code's envelope is always an object -> anomalous/tamper-shaped -> fail CLOSED.
        _dispatch_fact(state_dir, "non_object_payload",
                       f"payload was {type(payload).__name__}, not a JSON object", blocked=True,
                       ids=_ids_from_raw(payload_raw))
        return 2
    # The OTHER surrogate door: a payload whose bytes were valid UTF-8 but whose JSON text carried
    # an unpaired `\uD8xx` escape, which json.loads faithfully materializes as a real lone
    # surrogate. wire.read_stdin cannot see that one -- the escape is plain ASCII in the raw text --
    # so the parsed object is scrubbed here, and payload_raw is re-derived from the scrubbed object
    # so the text that gets persisted and keyword-scanned is the text that was actually evaluated.
    payload, escaped = wire.scrub(payload)
    if escaped:
        payload_raw = json.dumps(payload, ensure_ascii=False)
    if undecodable or escaped:
        # Recorded, not silent, and NOT a loud-allow: the payload was repaired and evaluation
        # continues normally. Distinguishing "repaired and checked" from "gave up and allowed" is
        # the whole difference between this row and the crash row it replaces.
        _dispatch_fact(state_dir, "unencodable_input",
                       f"replaced {undecodable} undecodable byte(s) and {escaped} unpaired "
                       f"surrogate escape(s); evaluation continued on the repaired payload",
                       blocked=False, disposition="REPAIRED", ids=_ids_from_payload(payload))
    # The host-dialect boundary (makoto.core.hostdialect): one hop from whatever spelling the
    # host sent to the protocol every reader below assumes, applied here -- after the envelope
    # has been proven evaluable (parseable, an object), before ANYTHING routes on or persists it
    # -- so routing, gates, history, commitments and audit all see one canonical payload rather
    # than each learning a second dialect. Cursor loads Claude-Code-compatible hook wiring but
    # delivers camelCase (`preToolUse`): under the wildcard-law routing that ran the WRONG
    # handler and persisted a row every history decoder was blind to (#19). The unevaluable-
    # envelope refusals ABOVE are untouched: this normalizes a known event's capitalization, and
    # `canonical_event` can only return a name already in HANDLERS, so a genuinely unknown event
    # still takes exactly the wildcard path it took before.
    host_event = payload.get("hook_event_name")
    payload, dialect_notes = hostdialect.normalize_payload(payload, HANDLERS)
    # A THIRD surrogate door, and the reason this scrub is here rather than only above.
    # `hostdialect._tool_result` runs `json.loads` on Cursor's `tool_output`, which arrives as a
    # JSON *string*. An unpaired `\ud800` escape inside that inner document is plain ASCII in the
    # outer payload -- invisible to `wire.read_stdin`, and invisible to the `wire.scrub` above,
    # because at that point it is still an unparsed string. Normalization is what materializes it,
    # so normalization is what has to be followed by a scrub. Verified by reproducing the ORIGINAL
    # UnicodeEncodeError on a camelCase envelope after the boundary fix was already in place: the
    # ensure_ascii=False reserialization below then carried the live surrogate straight into the
    # sqlite3 bind. Found by an independent review pass, not by the tests that existed.
    payload, dialect_escaped = wire.scrub(payload)
    if dialect_escaped:
        _dispatch_fact(state_dir, "unencodable_input",
                       f"replaced {dialect_escaped} unpaired surrogate escape(s) materialized by "
                       f"host-dialect normalization; evaluation continued on the repaired payload",
                       blocked=False, disposition="REPAIRED", ids=_ids_from_payload(payload))
    if dialect_notes:
        # Persist WHAT WAS EVALUATED, not the host's spelling of it. The events table is the
        # rolling substrate every history decoder reads, and those decoders key on the PAYLOAD's
        # `hook_event_name`/`tool_name` -- ingesting the raw dialect envelope would leave
        # `event.identical_retry`, `canon.recur`/`canon.timeout` and the claim-graph Bash
        # evidence path reading zero matching rows for a Cursor session: admitted live, then
        # invisible to every history-derived gate afterwards. Only rewritten when normalization
        # actually changed something: a host already speaking the protocol still ingests its own
        # bytes, byte-identical.
        # ensure_ascii=False: the default escapes non-ASCII to \uXXXX, and this text is also what
        # `_keyword_hit` prefilters the Pre catalog against as a raw substring scan -- an escaped
        # row would make a non-ASCII keyword match on a protocol host and silently miss on a
        # dialect host, the exact "a check that reads nothing" failure mode this boundary exists
        # to prevent.
        payload_raw = json.dumps(payload, ensure_ascii=False)
        _note_host_dialect(state_dir, payload.get("session_id"), dialect_notes, host_event)
    db_path = state_dir / "makoto.record.db"
    if not _ensure_db_initialized(state_dir, db_path):
        _dispatch_fact(state_dir, "db_init_failed", "lazy DB init failed", blocked=False,
                       ids=_ids_from_payload(payload))
        return 0  # transient infra -> loud-allow
    conn = _connect_with_retry(db_path)
    if conn is None:
        _dispatch_fact(state_dir, "db_locked", "write lock not acquired within retry budget",
                       blocked=False, ids=_ids_from_payload(payload))
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
        _dispatch_fact(state_dir, "exception", f"{type(exc).__name__}: {exc}", blocked=False,
                       ids=_ids_from_payload(payload))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
