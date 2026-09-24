"""append-only observability log — JSONL writer + structured error log.

Three append-only file outputs under the caller's state root:
- audit.jsonl           : one row per Finding-producing dispatcher invocation
- dispatch_errors.jsonl : one row per predicate that raised an unexpected exception
- exemptions.jsonl      : one row per REAL match suppressed by an agent escape valve
All three streams are chain-appended, so ledger's own chain.jsonl + chain.lock land in that same
root (see `_chain_then_append`).

Concurrent appends lean on O_APPEND short-write atomicity, which holds only while a row stays
inside the atomic write unit (~PIPE_BUF, 4KB): true of an error or exemption row, NOT guaranteed
of an audit row, whose `findings` list carries every finding's message AND snippet.

Write-only in production: no plugin code reads these logs back (a human or external tool reads
the jsonl files directly), so this module carries no readers.
"""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class AuditRow:
    """one append-only observability record per dispatch invocation.

    tool_name: the Claude Code tool that triggered the hook (e.g. "Write", "Edit", "Bash"),
    extracted so downstream mining can group fires by tool without re-parsing the raw event.
    Empty string when the payload omits it (Stop events, malformed payloads).
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
    oversight_clamp: dict | None = None    # {"active", "configured_mode", "permission_mode"}
    #   when posture.is_oversight_clamped fired for this event, else None. Additive: existing
    #   readers use dict.get, so old rows without this key parse fine.


def _append_jsonl(state_root: Path, filename: str, obj: dict) -> None:
    """serialize obj to compact JSON and append one line to <state_root>/<filename>.

    Creates state_root if missing. Short append-mode writes (<= PIPE_BUF, ~4KB) do not
    interleave between concurrent hook processes; a row ABOVE that size carries no such
    guarantee. The sole writer for all three append-only logs.
    """
    state_root.mkdir(parents=True, exist_ok=True)
    log = state_root / filename
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, separators=(",", ":")) + "\n")


def append_row(state_root: Path, row: AuditRow) -> None:
    """serialize row to JSON and append one line to <state_root>/audit.jsonl.

    The SAME row also goes to the chained, tamper-evident stream under kind="audit" via
    `_chain_then_append`. The root is passed EXPLICITLY, never an env var, so the chain write
    lands in exactly the caller's root, not wherever MAKOTO_STATE_DIR happens to point.
    """
    _chain_then_append(state_root, "audit.jsonl", "audit", asdict(row))


def _chain_then_append(state_root: Path, filename: str, structural_kind: str,
                       obj: dict, chain_payload: dict | None = None) -> None:
    """The one chain-then-file write path both append-only logs share. Chain-appends
    `chain_payload` (default: obj) under the structural `kind`; `prev_hash`/`row_hash` come back
    ADDITIVE on the jsonl line (readers use dict.get; history is never rewritten). A chain-append
    fault must never block the file log -- caught and swallowed; the jsonl file gets its row
    either way."""
    try:
        from makoto.state import ledger as _ledger
        payload = chain_payload if chain_payload is not None else obj
        chained = _ledger.append({"kind": structural_kind, **payload}, root=state_root)
        obj["prev_hash"] = chained.get("prev_hash", "")
        obj["row_hash"] = chained.get("row_hash", "")
    except Exception:
        pass
    _append_jsonl(state_root, filename, obj)


def append_error(state_root: Path, event_id: int | None,
                 pattern_id: str | None, exc: BaseException,
                 *, session_id: str = "", tool_name: str = "",
                 hook_event: str = "", id_source: str = "") -> None:
    """append one JSON line to <state_root>/dispatch_errors.jsonl on predicate or dispatch failure.

    SEPARATE from audit.jsonl; AuditRow shape preserved.
    Schema: {ts, plugin, event_id, pattern_id, exc_type, exc_message, session_id, tool_name,
    hook_event, id_source}.

    The attribution fields (`session_id`, `tool_name`) are the point: every row here is a check
    that did NOT run, so without them "did this failure affect the session I'm looking at?" is
    unanswerable after the fact.

    `id_source` records HOW the ids were obtained, since on the unparseable-payload path they
    can't come from a parsed envelope: "payload" (parsed object), "raw-scan" (recovered by
    scanning raw stdin text), "" (none available). A recovered id that doesn't say so is worse
    than no id.

    `plugin` names the author, since several sibling plugins can all emit a deny on the same
    hook, making an unattributed row unattributable once more than one is installed.

    Additive: every field is keyword-only with a default, and readers use dict.get, so
    pre-upgrade rows keep parsing identically.
    """
    _chain_then_append(state_root, "dispatch_errors.jsonl", "dispatch-error", {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "plugin": "makoto",
        "event_id": event_id,
        "pattern_id": pattern_id,
        "exc_type": type(exc).__name__,
        "exc_message": str(exc),
        "session_id": session_id,
        "tool_name": tool_name,
        "hook_event": hook_event,
        "id_source": id_source,
    })


def append_exemption(state_root: Path, *, pattern_id: str, kind: str, file: str,
                     line: int, reason: str, snippet: str = "",
                     session_id: str = "", tool_name: str = "") -> None:
    """append one JSON line to <state_root>/exemptions.jsonl — an on-the-record, auditable
    trace that a REAL match was suppressed by an agent escape valve.

    SEPARATE from audit.jsonl and dispatch_errors.jsonl. `kind` is the suppression mechanism:
    'makoto-allow' (a `makoto-allow: <reason>` marker on a flagged shape) or 'disabled-pattern'
    (a keyword-matched pattern muted via MAKOTO_DISABLE_PATTERNS). The escape valve stays open —
    it can no longer be silent.

    Also chain-appended (kind="exemption", root=state_root) so the receipt emitter's
    exemption_count cites a real `verify_chain`-backed row. Chain wiring and its fault tolerance
    are `_chain_then_append`'s, shared with append_row.
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
    # obj's own "kind" field is the SUPPRESSION mechanism ('makoto-allow'/'disabled-pattern'),
    # which collides with the chain row's STRUCTURAL kind ("exemption") -- renamed to
    # exemption_kind in the chain payload only; the exemptions.jsonl line's own "kind" is untouched.
    chain_payload = obj.copy()
    chain_payload["exemption_kind"] = chain_payload.pop("kind")
    _chain_then_append(state_root, "exemptions.jsonl", "exemption", obj, chain_payload)


