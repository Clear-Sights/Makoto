"""append-only observability log — JSONL writer + reader + structured error log.

Two file outputs under $MAKOTO_STATE_DIR/:
- audit.jsonl           : one row per Finding-producing dispatcher invocation (only-fires policy, 1.0.2)
- dispatch_errors.jsonl : one row per predicate that raised an unexpected exception

Both are append-only, line-delimited JSON, safe for concurrent appends under POSIX
PIPE_BUF semantics (rows are well under 4KB).

The 1.0.3 collapse pass removed summarize() / read_recent_events() and the
`makoto audit summary|tail|filter` CLI — `jq < audit.jsonl` covers ad-hoc queries
and nobody was running the aggregator subcommand.
"""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


@dataclass
class AuditRow:
    """one append-only observability record per dispatch invocation.

    tool_name (1.0.2+): the Claude Code tool that triggered the hook (e.g. "Write",
    "Edit", "Bash"). Extracted from the hook payload so downstream mining can group
    fires by tool without re-parsing the raw event. Empty string when the payload
    omits tool_name (Stop events, malformed payloads).
    """
    ts: str
    event: str
    hook_kind: str
    session_id: str
    project_root: str
    pattern_fires: list[str]
    exit_code: int
    retry_hint_emitted: bool
    findings: list[dict]
    tool_name: str = ""
    oversight_clamp: dict | None = None    # D6: {"active", "configured_mode", "permission_mode"}
    #   when posture.is_oversight_clamped fired for this event -- None otherwise (the common
    #   case). Additive: existing readers use dict.get, so old rows without this key parse fine.


def _append_jsonl(state_root: Path, filename: str, obj: dict) -> None:
    """serialize obj to compact JSON and append one line to <state_root>/<filename>.

    Creates state_root if missing. POSIX guarantees atomicity for short append-mode
    writes (<= PIPE_BUF, ~4KB); one row is well under, so concurrent appends don't
    interleave. The sole writer for both append-only logs (append_row + append_error).
    """
    state_root.mkdir(parents=True, exist_ok=True)
    log = state_root / filename
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, separators=(",", ":")) + "\n")


def append_row(state_root: Path, row: AuditRow) -> None:
    """serialize row to JSON and append one line to <state_root>/audit.jsonl.

    Task 2 slice 3b (owner decision: unify -- every dispatch audit row is chain-appended). The
    SAME row is also appended to the chained, tamper-evident stream via
    `ledger.append(..., root=state_root)` (an explicit root, per FABLE DECISION 2026-07-07 --
    audit.py's whole contract is an explicit `state_root`, never an env var, so the chain write
    must land in exactly the caller's root, not wherever MAKOTO_STATE_DIR happens to point).
    `prev_hash`/`row_hash` come back ADDITIVE on the audit.jsonl line -- existing readers use
    dict.get, so pre-upgrade rows without these keys keep parsing identically, and audit.jsonl's
    own history is NEVER rewritten (append-only law); the chain simply starts accumulating from
    the first post-upgrade row onward. A chain-append fault must never block the older, more
    foundational fires log -- caught and swallowed; audit.jsonl still gets its row either way.
    """
    obj = asdict(row)
    try:
        from makoto import ledger as _ledger
        chained = _ledger.append({"kind": "audit", **obj}, root=state_root)
        obj["prev_hash"] = chained.get("prev_hash", "")
        obj["row_hash"] = chained.get("row_hash", "")
    except Exception:
        pass
    _append_jsonl(state_root, "audit.jsonl", obj)


def _read_jsonl(state_root: Path, filename: str, since: str | None) -> Iterator[dict]:
    """stream <state_root>/<filename> line by line, yielding one dict per valid JSON row. Missing
    file -> empty; blank/malformed lines skipped; optional ISO-8601 `since` filters by `ts`. The one
    reader both append-only logs share (read_rows + read_exemptions), so neither restates the loop."""
    log = state_root / filename
    if not log.exists():
        return
    with log.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since is not None and row.get("ts", "") < since:
                continue
            yield row


def read_rows(state_root: Path, since: str | None = None) -> Iterator[dict]:
    """stream the audit (fires) log; one dict per valid JSON row. See _read_jsonl for the contract."""
    yield from _read_jsonl(state_root, "audit.jsonl", since)


def append_error(state_root: Path, event_id: int | None,
                 pattern_id: str | None, exc: BaseException) -> None:
    """append one JSON line to <state_root>/dispatch_errors.jsonl on predicate failure.

    Spec §5.7 + v5 fix #9. SEPARATE from audit.jsonl; AuditRow shape preserved.
    Schema: {ts, event_id, pattern_id, exc_type, exc_message}. Called by
    _dispatch._run_predicates when a predicate import or call raises (fail-open).
    """
    _append_jsonl(state_root, "dispatch_errors.jsonl", {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_id": event_id,
        "pattern_id": pattern_id,
        "exc_type": type(exc).__name__,
        "exc_message": str(exc),
    })


def append_exemption(state_root: Path, *, pattern_id: str, kind: str, file: str,
                     line: int, reason: str, snippet: str = "",
                     session_id: str = "", tool_name: str = "") -> None:
    """append one JSON line to <state_root>/exemptions.jsonl — an on-the-record, auditable
    trace that a REAL match was suppressed by an agent escape valve.

    SEPARATE from audit.jsonl (the fires log, whose counts scripts/expected_fires.json pins) and
    from dispatch_errors.jsonl (predicate faults). `kind` is the suppression mechanism:
    'makoto-allow' (a `makoto-allow: <reason>` marker on a flagged shape) or 'disabled-pattern'
    (a keyword-matched pattern muted via MAKOTO_DISABLE_PATTERNS). The escape valve stays open —
    it can no longer be silent. This makes claim C3 ('on-the-record, auditable rationale, never a
    disguise') hold against the audit stream, not only the in-source annotation.

    Task 2 slice 4 (Fable-flagged gap, closed): also chain-appended (kind="exemption", root=
    state_root) so the receipt emitter's exemption_count cites a real `verify_chain`-backed row
    instead of an unchained file the receipt's own "every line re-runnable" claim couldn't honor.
    Same fault-tolerance as append_row's chain wire: a chain fault never blocks this write.
    """
    obj = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "kind": kind,
        "pattern_id": pattern_id,
        "file": file,
        "line": line,
        "reason": reason,
        "snippet": snippet,
        "session_id": session_id,
        "tool_name": tool_name,
    }
    try:
        from makoto import ledger as _ledger
        # obj's own "kind" field is the SUPPRESSION mechanism ('makoto-allow'/'disabled-pattern'),
        # which collides with the chain row's STRUCTURAL kind ("exemption") -- renamed to
        # exemption_kind in the chain payload only; the audit.jsonl line's own "kind" is untouched.
        chain_payload = {k: v for k, v in obj.items() if k != "kind"}
        chain_payload["exemption_kind"] = obj["kind"]
        chained = _ledger.append({"kind": "exemption", **chain_payload}, root=state_root)
        obj["prev_hash"] = chained.get("prev_hash", "")
        obj["row_hash"] = chained.get("row_hash", "")
    except Exception:
        pass
    _append_jsonl(state_root, "exemptions.jsonl", obj)


def read_exemptions(state_root: Path, since: str | None = None) -> Iterator[dict]:
    """stream the exemptions log; the reader that keeps it from being a write-only artifact — an
    exemption nobody can review would be its own illusory word. See _read_jsonl for the contract."""
    yield from _read_jsonl(state_root, "exemptions.jsonl", since)
