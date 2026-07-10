"""ackblock: Task 2 slice 5 -- the discharge mechanism for session-level canon fingerprints
(FABLE DECISION 2026-07-07, recorded verbatim in the plan). A SESSION-LEVEL fingerprint
(gate.canon_fingerprints) matches over the whole recorded call stream; once its atoms go true
they stay true forever (recorded history is immutable), so without a real discharge path it
becomes a PERMANENT block for the rest of the session after any one matching action -- even a
fully owner-sanctioned one. Rejected discharges: narrowing the detector (voids the 0-FP
certificate + teaches a gaming recipe), and operator self-disable (normalizes the one action
Makoto must never normalize). The decided discharge: an OPERATOR-ATTRIBUTABLE
`release.operator` record, never prose, never atom-narrowing.

D8a (docs/DEFERRED.md, FABLE DECISION 2026-07-08, rename-only, owner-authorized 2026-07-08):
this mechanism is the `release.operator` tier of Makoto's `release` family (`release.green` --
world-verified, agent-earnable -- is a distinct, not-yet-built future item; this module
implements ONLY the host-transcript-attributed tier). Epoch reset (2026-07-10, owner
decision): the phrase a human types and the chain `kind` are EXACTLY `release.operator` -- the
former accept-the-original-forever guarantee (and the alias-table discipline it mirrored) was
retired outright; state predating the reset is archived (zip) or wiped by the operator, so no
record remains whose meaning depends on the old forms.

SPOOF-PROOF ATTRIBUTION (the load-bearing part): the ack is NEVER trusted from ledger/chain
content -- at CHECK TIME Makoto re-derives it from the HOST-WRITTEN transcript file every time.
A transcript entry is a valid ack iff it:
  1. has top-level role "user" (`entry["message"]["role"] == "user"`, real transcript shape --
     confirmed against this session's own transcript JSONL, 2026-07-07);
  2. carries NO `toolUseResult` field (excludes tool-result turns -- the only agent-producible
     user-role entries; a tool call cannot write a top-level `toolUseResult`-free user turn);
  3. is not synthetic/system-injected -- no `<system-reminder`/hook-output/task-notification
     marker, and not the harness's own "[Request interrupted by user]" synthetic text;
  4. is timestamped AFTER the fingerprint's first-fired ts in THIS session (derived from the
     chain's own unified audit trail -- slice 3b -- never from prose);
  5. contains the literal token `makoto release.operator <fingerprint-id>` plus a nonempty
     reason naming that exact id.
No agent tool call, subagent output, or file write can forge such an entry -- the transcript is
host-written, never model-written. A found ack is chain-appended (kind="release.operator")
for the receipt/audit trail, but the DISCHARGE
decision itself is re-derived from the transcript on every evaluation, never read back from that
row (`record_ack_block_if_new` only avoids duplicate chain rows across repeated Stops -- see its
own docstring).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from makoto.record import ledger
_ACK_RX = re.compile(
    r"makoto\s+release\.operator\s+([^\s:]+)\s*[:\-]?\s*(.+)", re.I)
# [^\s:]+ (not \S+) for the id group: \S+ is greedy enough to swallow the separating colon
# itself (id becomes "name:", never matching the real fingerprint id) -- found live by
# test_genuine_ack_after_first_fired_discharges/test_ack_rejected_when_reason_is_empty, which
# also caught the mirror bug (an id-only ack with nothing after the colon matching "" -> ":" as
# a non-empty-looking "reason" via backtracking). Excluding ':' from the id group closes both.
# Epoch reset (2026-07-10, owner decision): `release.operator` is the ONLY discharge phrase.
# The former dual-phrase acceptance existed to keep pre-rename records/habits working; the owner
# retired that guarantee outright -- state predating the reset is archived (zip) or wiped, so
# there is no history left whose meaning depends on the old phrase."""
_SYNTHETIC_MARKERS = (
    "<system-reminder", "<user-prompt-submit-hook", "<task-notification",
    "<local-command-caveat", "[request interrupted by user]",
)


def _entry_text(entry: dict) -> str:
    msg = entry.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text", "")) for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return ""


def _is_genuine_user_turn(entry: dict) -> Optional[str]:
    """Return the entry's text iff it is a genuine, host-written, non-synthetic user turn (ack
    contract points 1-3) -- else None. A tool result or a synthetic/system-injected turn can
    never qualify, no matter what text it happens to contain."""
    msg = entry.get("message")
    if not isinstance(msg, dict) or msg.get("role") != "user":
        return None
    if "toolUseResult" in entry:
        return None
    text = _entry_text(entry)
    low = text.lower()
    if any(marker in low for marker in _SYNTHETIC_MARKERS):
        return None
    return text


def _first_fired_ts(fingerprint_id: str, *, gate_pattern_id: str = "gate.canon_fingerprints",
                    session_id: Optional[str] = None,
                    root: Optional[Path] = None) -> Optional[str]:
    """The earliest chain-recorded ts at which `gate_pattern_id` fired NAMING fingerprint_id,
    read from the unified audit trail (slice 3b -- every dispatch audit row is chain-appended).
    None if it has never fired in this chain. Chronological order is the chain's own append
    order, so the first match IS the earliest. `gate_pattern_id` generalizes this beyond
    gate.canon_fingerprints (Task 0b: gate.canon's canon.timeout has the SAME no-discharge shape
    when the last error is a genuinely unresolvable, operator-surfaced block -- one mechanism,
    two gates, per SPEC-C's "one mercy model")."""
    needle = f"canon.{fingerprint_id}:"
    for row in ledger.read(root=root):
        if row.get("kind") != "audit":
            continue
        if session_id is not None and row.get("session_id") != session_id:
            continue
        if gate_pattern_id not in (row.get("pattern_fires") or []):
            continue
        for finding in row.get("findings") or ():
            if needle in (finding.get("message") or ""):
                return row.get("ts")
    return None


def find_ack_block(fingerprint_id: str, *, transcript_path: Optional[str],
                   gate_pattern_id: str = "gate.canon_fingerprints",
                   session_id: Optional[str] = None,
                   root: Optional[Path] = None) -> Optional[dict]:
    """Scan the host-written transcript at `transcript_path` for a qualifying release.operator turn for
    `fingerprint_id` (fired under `gate_pattern_id`). Returns {"fingerprint_id", "reason", "ts"}
    for the FIRST qualifying turn found, or None. Never raises: an absent/unreadable transcript
    or an unfired fingerprint (no first-fired ts to compare against) both read as "no ack" --
    fail-closed on the BLOCK side, which is the safe direction (a discharge must be earned, never
    assumed)."""
    if not transcript_path:
        return None
    since_ts = _first_fired_ts(fingerprint_id, gate_pattern_id=gate_pattern_id,
                               session_id=session_id, root=root)
    if since_ts is None:
        return None
    p = Path(transcript_path)
    if not p.exists():
        return None
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        text = _is_genuine_user_turn(entry)
        if text is None:
            continue
        ts = entry.get("timestamp", "")
        if not ts or ts <= since_ts:
            continue
        m = _ACK_RX.search(text)
        if not m:
            continue
        # group(2) can still capture a bare leftover separator (e.g. id-only "notestedit_destruct:"
        # backtracks to reason=":") when nothing real follows -- strip stray leading punctuation
        # before the truthiness check, rather than trust the regex to have consumed it.
        acked_id = m.group(1).strip()
        reason = m.group(2).strip().lstrip(":- ").strip()
        if acked_id != fingerprint_id or not reason:
            continue
        return {"fingerprint_id": fingerprint_id, "reason": reason, "ts": ts}
    return None


# Epoch reset (2026-07-10): exactly one chain kind means "an operator-attributed release".
_RELEASE_OPERATOR_KINDS = frozenset({"release.operator"})


def record_ack_block_if_new(ack: dict, *, session_id: Optional[str] = None,
                            root: Optional[Path] = None) -> bool:
    """Chain-append a `release.operator` row for `ack` (kind="release.operator") UNLESS this
    exact (fingerprint_id, session_id) pair is already recorded -- avoids flooding the chain with a duplicate row on every
    subsequent Stop for the rest of the session (the ack is re-derived from the transcript every
    time regardless; this is purely the audit/receipt trail, never the discharge decision
    itself). Returns True iff a new row was appended. Never raises: a chain fault must not block
    the Stop-gate evaluation it accompanies."""
    try:
        for row in ledger.read(root=root):
            if (row.get("kind") in _RELEASE_OPERATOR_KINDS
                    and row.get("fingerprint_id") == ack["fingerprint_id"]
                    and row.get("session_id") == session_id):
                return False
        ledger.append({
            "kind": "release.operator",
            "fingerprint_id": ack["fingerprint_id"],
            "reason": ack["reason"],
            "acked_at": ack["ts"],
            "session_id": session_id,
        }, root=root)
        return True
    except Exception:
        return False
