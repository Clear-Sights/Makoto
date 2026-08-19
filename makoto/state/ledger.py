"""Results ledger: record `update`s and read them back by key.

An `update` records a result-producing operation's outcome, keyed by the
normalized location it concerns; latest-wins (a retest supersedes, never fires).
Reuses the verified real-payload extractor `lib.io.bash_output_text` so we
read the fields the live hook actually emits — never a hand-built shape.

Pure data layer: callers pass an open sqlite3 connection whose `ledger` table
matches db.py's schema (key, value, kind, exit, source_event_id, session_id, ts).
"""
import re

from makoto.checks import normalize_path
from makoto.kit import bash_output_text, is_test_runner

_PATH_IN_CMD_RX = re.compile(r"[\w.\-]+/[\w.\-]+\.\w+|`?([\w.\-]+\.\w+)`?")


def _bash_key(ev: dict) -> str:
    """Best-effort location a Bash run concerns: a path-shaped token in the
    command, else the cwd, else a stable 'bash' fallback (stated, not inferred)."""
    cmd = ev.get("tool_input", {}).get("command", "") or ""
    m = _PATH_IN_CMD_RX.search(cmd)
    if m:
        return normalize_path(m.group(0))
    return normalize_path(ev.get("cwd", "")) or "bash"


def record_update(conn, ev: dict, *, event_id: int, session_id: str, root=None) -> None:
    """Record one update from a PostToolUse event. Write/Edit -> a `touched` row;
    Bash -> a `value` row with extracted output + exit code. Latest-wins in sqlite;
    ALSO chain-appended (Task 2 part 2 -- closing the shared Record schema, same unify pattern
    as audit.append_row/slice 3b): sqlite stays the latest-wins query index, the chain preserves
    every update sqlite's upsert would otherwise overwrite-and-lose. `root` overrides env-var
    resolution for the chain write only (see `store_root`); sqlite's own root always comes from
    `conn`, unaffected."""
    tool = ev.get("tool_name", "")
    if tool in ("Write", "Edit", "MultiEdit"):
        key = normalize_path(ev.get("tool_input", {}).get("file_path", ""))
        if not key:
            return
        # §7.1 content-depth: a Write states the file's FULL content, so record its stripped
        # length ("0" == a zero-byte production) — the completion gate reads this to tell a
        # real "I produced X" from a hollow one. Edit/MultiEdit only PATCH existing content
        # (the file is not zero-byte just because a patch is small), so they stay value=None.
        value = None
        if tool == "Write":
            content = ev.get("tool_input", {}).get("content", "")
            value = str(len((content or "").strip()))
        _upsert(conn, key, "touched", value, None, event_id, session_id, root=root)
    elif tool == "Bash":
        tr = ev.get("tool_response", {})
        text = bash_output_text(tr)   # internally type-dispatches; non-dict/list/str -> ""
        exit_code = tr.get("exitCode", tr.get("exit")) if isinstance(tr, dict) else None
        # A test-runner command files its output under kind='testrun' — the green-claim gate
        # (gates.green_claim_gate) reads ONLY these rows, so a `cat failing.log` that merely PRINTS
        # "=== 3 failed ===" is never consulted (the cat-a-log FP firewall). Store the OUTPUT TAIL,
        # where the pass/fail VERDICT ('=== N failed/passed in Xs ===') always lives; any other Bash
        # stays kind='value' with the head, exactly as before.
        cmd = ev.get("tool_input", {}).get("command", "") or ""
        if is_test_runner(cmd):
            _upsert(conn, _bash_key(ev), "testrun", text[-500:], exit_code, event_id, session_id, root=root)
        else:
            _upsert(conn, _bash_key(ev), "value", text[:500], exit_code, event_id, session_id, root=root)


def _upsert(conn, key, kind, value, exit_code, event_id, session_id, *, root=None) -> None:
    conn.execute(
        "INSERT INTO ledger (key, value, kind, exit, source_event_id, session_id, ts) "
        "VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, kind=excluded.kind, "
        "exit=excluded.exit, source_event_id=excluded.source_event_id, "
        "session_id=excluded.session_id, ts=excluded.ts",
        [key, value, kind, exit_code, event_id, session_id],
    )
    conn.commit()
    # chain-append the pre-upsert row too (append-only -- preserves what the sqlite upsert is
    # about to overwrite). ONLY when `root` is explicitly given: unlike ledger.append's own
    # additive-default contract (env-var fallback, design-decided for that layer), this convenience
    # wire is NEW here, and record_update has many pre-existing bare unit-test call sites with no
    # state-dir isolation at all -- guessing a default root for them would leak chain writes into
    # the real environment. root=None means "no chain append attempted", not "guess a location".
    # A chain fault must never block the sqlite write it accompanies either way.
    if root is not None:
        try:
            append({"kind": kind, "key": key, "value": value, "exit": exit_code,
                    "source_event_id": event_id, "session_id": session_id}, root=root)
        except Exception:
            pass


def read_key(conn, key: str):
    """Read the latest ledger row for a normalized key, or None."""
    r = conn.execute(
        "SELECT key, value, kind, exit, source_event_id FROM ledger WHERE key = ?",
        [normalize_path(key)],
    ).fetchone()
    if not r:
        return None
    return {"key": r[0], "value": r[1], "kind": r[2], "exit": r[3], "source_event_id": r[4]}


def touched_keys(conn, session_id: str) -> set:
    """locations this session has recorded results/touches for (ledger keys)."""
    try:
        rows = conn.execute(
            "SELECT key FROM ledger WHERE session_id = ?", [session_id]).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def empty_write_keys(conn, session_id: str) -> set:
    """Locations whose latest recorded Write produced zero substance (a 'touched' row with
    value '0', §7.1) — the content-depth signal for the completion/advance gates. Fail-open."""
    try:
        rows = conn.execute(
            "SELECT key FROM ledger WHERE session_id = ? AND kind = 'touched' AND value = '0'",
            [session_id]).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


class LedgerView:
    """Thin read-surface FACADE over one (conn, session_id) pair (SPEC-5 Task 2's unified
    read surface, `ledger.view_for`) — every check module (Tasks 3-9) reads its ledger state
    through this, rather than hand-rolling its own SQL. Delegates to this module's existing
    module-level functions verbatim; it adds no new SQL and changes no existing behavior.

    Built once per (conn, session_id) and handed to a check the same way GateContext is: a
    small bag of already-resolved facts, not a live query object a check pokes ad hoc."""

    def __init__(self, conn, session_id: str):
        self._conn = conn
        self._session_id = session_id

    def touched_keys(self) -> set:
        return touched_keys(self._conn, self._session_id)

    def empty_write_keys(self) -> set:
        return empty_write_keys(self._conn, self._session_id)

    def latest_testrun(self) -> str:
        return latest_testrun(self._conn, self._session_id)

    def read_key(self, key: str):
        return read_key(self._conn, key)


def view_for(conn, session) -> "LedgerView":
    """Build the unified ledger read-surface for one session.

    `session` is either a bare session_id string, or an event/hook-payload dict carrying one
    under `"session_id"` (the same two shapes `dispatch.py` already juggles: a raw payload at
    the hook boundary, a bare `sid` once unpacked) — so a check can pass through whichever it
    already has in hand. A dict with no `session_id` key resolves to `""` (matches every
    existing ledger read function's fail-open-to-empty behavior for an unknown session), never
    raises.
    """
    session_id = session.get("session_id", "") if isinstance(session, dict) else (session or "")
    return LedgerView(conn, session_id)


def latest_testrun(conn, session_id: str) -> str:
    """The MOST RECENT recorded test-runner output for this session (the latest kind='testrun'
    ledger row's value), or '' if no test runner ran. Ordered by source_event_id (the monotonic,
    unique AUTOINCREMENT events.id assigned at record time, which the upsert ADVANCES on a same-key
    rerun) so a fix-and-rerun supersedes deterministically — NOT by `ts`, whose wall-clock value
    collides on fast replay and is non-monotonic across NTP/suspend, making the "latest" unstable
    (the cause of phantom green_claim fires that vanish on isolated replay). rowid is a final
    deterministic tiebreaker for total order. '' makes green_claim_gate inert."""
    try:
        r = conn.execute(
            "SELECT value FROM ledger WHERE session_id = ? AND kind = 'testrun' "
            "ORDER BY source_event_id DESC, rowid DESC LIMIT 1", [session_id]).fetchone()
        return (r[0] or "") if r else ""
    except Exception:
        return ""


# =============================================================================================
# The chained, tamper-evident surface (owner decision 2026-07-07: verification lives IN the
# ledger — the gates' verdicts depend on these rows, so the store and its verifier share one
# home). Ported by shape from Assay's kernel/ledger.py + identity (the substrate the SPEC-5
# merge dropped), re-homed onto makoto.state.store._state_dir(). Append-only JSONL with
# prev_hash/row_hash links; verify_chain names the exact broken row; an exclusive fcntl.flock
# across tail-read+append means concurrent hook invocations can never fork the chain.
# Relationship to the sqlite surface above: sqlite stays the latest-wins QUERY INDEX; this is
# the tamper-evident RECORD. Two surfaces, one module, no third store (rule 5).
# =============================================================================================
import fcntl
import hashlib
import json as _json
from pathlib import Path
from typing import Optional

from makoto.state.store import _state_dir as _chain_state_dir

_DEFAULT_STREAM = "chain"
OPEN = "open"


def norm_sha256(content: str) -> str:
    """sha256 of the per-line-rstripped normalization of `content` — a reformat that changes only
    trailing whitespace hashes identically, an internal-whitespace change does not. 64-char hex."""
    normalized = "\n".join(line.rstrip() for line in content.splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _dumps(row: dict) -> str:
    """The one byte-stable JSON line every write shares: sorted keys, unicode kept, compact."""
    return _json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical(row: dict) -> str:
    """The chain's hash input: the row's structural fields EXCLUDING `row_hash` (a row cannot hash
    its own hash), `prev_hash` INCLUDED so the link binds to chain position. Sorted-key bytes."""
    return _dumps({k: v for k, v in row.items() if k != "row_hash"})


def _row_hash(prev_hash: str, row: dict) -> str:
    return norm_sha256(prev_hash + canonical(row))


def store_root(*, root: Optional[Path] = None) -> Path:
    """Makoto's resolved state home (`state._state_dir()`) — the one root writer and reader share.
    `root`, when given, overrides env-var resolution entirely (additive -- every existing zero-arg
    call site keeps today's behavior unchanged). For a caller that already holds its own explicit
    state root (audit.py's whole contract is `state_root: Path` params, never env vars) rather
    than relying on `MAKOTO_STATE_DIR` -- DESIGN DECISION 2026-07-07 (Task 2 slice 3b): this beats
    a second, duplicate hash-chain implementation inside audit.py, which would let two copies of
    the canonicalization/hashing logic silently drift."""
    return root if root is not None else _chain_state_dir()


def _lock_path(root: Path, name: str) -> Path:
    return root / f"{name}.lock"


class _Locked:
    """Exclusive advisory lock over stream `name`'s content-free sidecar, held across the whole
    append (tail-read + write) so a concurrent append can never fork the chain."""

    def __init__(self, name: str, *, root: Optional[Path] = None):
        self._name = name
        self._root = root
        self._fh = None

    def __enter__(self):
        root = store_root(root=self._root)
        root.mkdir(parents=True, exist_ok=True)
        self._fh = open(_lock_path(root, self._name), "a+", encoding="utf-8")
        fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            self._fh.close()  # flock releases on close/process-exit
            self._fh = None


def read(*, name: str = _DEFAULT_STREAM, root: Optional[Path] = None) -> list:
    """The named stream as an ordered list of row dicts. `[]` when absent (presence-detection).
    A truncated/corrupt tail ends the read at that point — the well-formed PREFIX is returned,
    never a raised parse error. Does NOT verify the chain (that is `verify_chain`)."""
    target = store_root(root=root) / f"{name}.jsonl"
    if not target.exists():
        return []
    rows = []
    with open(target, "r", encoding="utf-8") as fh:
        for raw in fh:
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                rows.append(_json.loads(stripped))
            except ValueError:
                break
    return rows


def append(row: dict, *, name: str = _DEFAULT_STREAM, root: Optional[Path] = None) -> dict:
    """Append one row, computing its chain link — never rewrites an existing row. Holds the
    stream's exclusive lock across tail-read + append so the chain can never fork. Returns the
    stored row with `prev_hash`/`row_hash` populated. `root` overrides env-var resolution (see
    `store_root`)."""
    with _Locked(name, root=root):
        existing = read(name=name, root=root)
        prev_hash = existing[-1].get("row_hash", "") if existing else ""
        stored = dict(row)
        stored.setdefault("status", OPEN)
        stored["prev_hash"] = prev_hash
        stored.pop("row_hash", None)
        stored["row_hash"] = _row_hash(prev_hash, stored)
        target = store_root(root=root) / f"{name}.jsonl"
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(_dumps(stored) + "\n")
            fh.flush()
    return stored


def verify_chain(*, name: str = _DEFAULT_STREAM, root: Optional[Path] = None) -> Optional[int]:
    """Re-walk the whole stream, recomputing each row's expected `prev_hash`/`row_hash`. Returns
    None when every link verifies (including the vacuously-intact absent/empty stream), else the
    0-based index of the FIRST row that fails to parse, is not a dict, or whose link does not
    match — the exact point an edit, deletion, reorder, or truncation broke the chain. NEVER
    RAISES: an unreadable store reads as None. `root` overrides env-var resolution (see
    `store_root`) -- a caller verifying a chain it appended via an explicit root must pass the
    SAME root here, or it will resolve the wrong stream."""
    target = store_root(root=root) / f"{name}.jsonl"
    if not target.exists():
        return None
    try:
        with open(target, "r", encoding="utf-8") as fh:
            lines = list(fh)
    except OSError:
        return None
    expected_prev = ""
    idx = 0
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            row = _json.loads(stripped)
        except ValueError:
            return idx
        if not isinstance(row, dict):
            return idx
        if row.get("prev_hash", "") != expected_prev:
            return idx
        if row.get("row_hash") != _row_hash(expected_prev, row):
            return idx
        expected_prev = row.get("row_hash", "")
        idx += 1
    return None


# =============================================================================================
# ackblock (merged from record/ackblock.py -- Stage 2 seam 1)
_ACKBLOCK_DOC = """ackblock: Task 2 slice 5 -- the discharge mechanism for session-level canon fingerprints
(DESIGN DECISION 2026-07-07, recorded verbatim in the plan). A SESSION-LEVEL fingerprint
(gate.canon_fingerprints) matches over the whole recorded call stream; once its atoms go true
they stay true forever (recorded history is immutable), so without a real discharge path it
becomes a PERMANENT block for the rest of the session after any one matching action -- even a
fully owner-sanctioned one. Rejected discharges: narrowing the detector (voids the 0-FP
certificate + teaches a gaming recipe), and operator self-disable (normalizes the one action
Makoto must never normalize). The decided discharge: an OPERATOR-ATTRIBUTABLE
`release.operator` record, never prose, never atom-narrowing.

D8a (docs/DEFERRED.md, DESIGN DECISION 2026-07-08, rename-only, owner-authorized 2026-07-08):
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
import json
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


def user_turn_texts(transcript_path: Optional[str], *, limit: int = 4000) -> list:
    """Every genuine, host-written, non-synthetic user turn in the transcript, oldest first.

    The ORACLE channel, exposed for readers other than the ack scanner. `find_ack_block` has always
    needed "what did the human actually type, as opposed to what could the agent have produced" --
    contract points 1-3 of the ack rules, enforced by `_is_genuine_user_turn`. That question is not
    specific to acks: any check that wants to distinguish a fact the human supplied from a fact the
    agent supplied needs exactly this list, and needs it to have the same spoof-resistance.

    Sharing the primitive rather than re-deriving it is the point. A second, looser reader of the
    transcript would be a second definition of "the user said so", and the looser one would win any
    disagreement -- which is how an agent-writable channel becomes an oracle by accident.

    Never raises: an absent, unreadable or malformed transcript reads as "no user turns". Callers
    must treat that as absence of evidence, never as evidence of absence.

    `limit` bounds the scan; a transcript is unbounded in principle and this runs on a hot path.
    """
    if not transcript_path:
        return []
    p = Path(transcript_path)
    try:
        if not p.exists():
            return []
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    texts = []
    for line in raw.splitlines()[:limit]:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        text = _is_genuine_user_turn(entry)
        if text:
            texts.append(text)
    return texts


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
    for row in read(root=root):
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
        for row in read(root=root):
            if (row.get("kind") in _RELEASE_OPERATOR_KINDS
                    and row.get("fingerprint_id") == ack["fingerprint_id"]
                    and row.get("session_id") == session_id):
                return False
        append({
            "kind": "release.operator",
            "fingerprint_id": ack["fingerprint_id"],
            "reason": ack["reason"],
            "acked_at": ack["ts"],
            "session_id": session_id,
        }, root=root)
        return True
    except Exception:
        return False


# =============================================================================================
# receipt (merged from record/receipt.py -- Stage 2 seam 1)
_RECEIPT_DOC = """The receipt emitter (Task 2 slice 4) -- Makoto blocks the illusory word but, until now,
issued no tender for the kept one; the README promises "trustworthy tender... without
re-deriving it" and nothing emitted it. This closes that gap.

DESIGN DECISION 2026-07-07 (curated brief: claim kinds, shape, persistence):
  1. Only `verdict`/`certified-fact`/`testrun` chain rows count as CLAIMS -- kinds that assert
     something about the world (the ancestor canon/mint.py's "spendable if backed by a real
     deed" test). `audit`/`touched`/`release.operator`/`fetch`/`exemption` are records of deeds and
     machinery, not claims, and folding them in would blur exactly the distinction the receipt
     exists to expose.
  2. One dict per call: {ts, session_id, chain_name, verified_through, claims, claim_count,
     trace_bound_count, exemption_count} -- a list of citations plus PARALLEL counts, never
     combined into one score (HOURGLASS: a measure you optimize for stops measuring). Every
     claim cites its own row_index/row_hash, independently re-checkable against `verify_chain`.
  3. A PURE READ-TIME VIEW -- nothing persisted. A 4th file to keep in sync, or a chain row that
     could only attest to a chain it is itself inside, both cut against this project's own "one
     stream, everything else a view" goal (SPEC-C item 1).

`trace_bound` = at or before `verified_through`'s cut (or every row, if the whole chain is
intact) -- a claim AFTER the first broken link can no longer be trusted to be what it claims to
be, so it is excluded from trace_bound_count (though still listed in `claims`, undisguised).
"""
_CLAIM_KINDS = frozenset({"verdict", "certified-fact", "testrun"})
_EXEMPTION_KIND = "exemption"


def _session_matches(row: dict, session_id: Optional[str]) -> bool:
    return session_id is None or row.get("session_id") == session_id


def _trace_bound(row_index: int, verified_through: Optional[int]) -> bool:
    return verified_through is None or row_index < verified_through


def emit_receipt(*, session_id: Optional[str] = None, name: str = "chain",
                 root: Optional[Path] = None) -> dict:
    """Compute one receipt over the chain at `root` (env-var default when None), optionally
    scoped to one `session_id`. Never raises: reads `ledger.read`/`verify_chain`, both of which
    are themselves never-raise (absent/empty chain -> a vacuous, all-zero receipt)."""
    rows = read(name=name, root=root)
    verified_through = verify_chain(name=name, root=root)

    claims = [
        {"claim_kind": row.get("kind"), "row_index": idx, "row_hash": row.get("row_hash", "")}
        for idx, row in enumerate(rows)
        if row.get("kind") in _CLAIM_KINDS and _session_matches(row, session_id)
    ]
    trace_bound_count = sum(1 for c in claims if _trace_bound(c["row_index"], verified_through))
    exemption_count = sum(
        1 for idx, row in enumerate(rows)
        if row.get("kind") == _EXEMPTION_KIND and _session_matches(row, session_id)
        and _trace_bound(idx, verified_through)
    )
    return {
        "session_id": session_id,
        "chain_name": name,
        "verified_through": verified_through,
        "claims": claims,
        "claim_count": len(claims),
        "trace_bound_count": trace_bound_count,
        "exemption_count": exemption_count,
    }
