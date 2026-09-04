"""Results ledger: record `update`s and read them back by key.

An `update` records a result-producing operation's outcome, keyed by the
normalized location it concerns; latest-wins (a retest supersedes, never fires).
Reuses the verified real-payload extractor `lib.io.bash_output_text` so we
read the fields the live hook actually emits — never a hand-built shape.

Pure data layer: callers pass an open sqlite3 connection whose `ledger` table
matches db.py's schema (key, value, kind, exit, source_event_id, session_id, ts),
keyed by (session_id, key).
"""
import re

from makoto.checks import normalize_path
from makoto.substrate.io import bash_output_text, is_test_runner

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
        "ON CONFLICT DO UPDATE SET value=excluded.value, kind=excluded.kind, "
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


def read_key(conn, key: str, session_id=None):
    """Read the latest ledger row for a key, optionally scoped to one session."""
    normalized = normalize_path(key)
    if session_id is None:
        r = conn.execute(
            "SELECT key, value, kind, exit, source_event_id FROM ledger WHERE key = ? "
            "ORDER BY source_event_id DESC, rowid DESC LIMIT 1",
            [normalized],
        ).fetchone()
    else:
        r = conn.execute(
            "SELECT key, value, kind, exit, source_event_id FROM ledger "
            "WHERE key = ? AND session_id = ?",
            [normalized, session_id],
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
        return read_key(self._conn, key, self._session_id)


def view_for(conn, session) -> "LedgerView":
    """Build the unified ledger read-surface for one session.

    `session` is either a bare session_id string, or an event/hook-payload dict carrying one
    under `"session_id"` (the same two shapes `_dispatch.py` already juggles: a raw payload at
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
# merge dropped), re-homed onto makoto.record.state._state_dir(). Append-only JSONL with
# prev_hash/row_hash links; verify_chain names the exact broken row; an exclusive fcntl.flock
# across tail-read+append means concurrent hook invocations can never fork the chain.
# Relationship to the sqlite surface above: sqlite stays the latest-wins QUERY INDEX; this is
# the tamper-evident RECORD. Two surfaces, one module, no third store (rule 5).
# =============================================================================================
import fcntl
import hashlib
import json as _json
import os
import tempfile
from pathlib import Path
from typing import Optional

from makoto.record.state import _state_dir as _chain_state_dir

_DEFAULT_STREAM = "chain"
OPEN = "open"

# Sidecar suffixes. Both hold the SAME triple -- {"rows": N, "head_hash": H, "bytes": B}, read
# as "the stream's first B bytes hold N well-formed rows, the last of which hashes to H" -- but
# they answer different questions and advance at different moments, so they are separate files:
#   .tail.json      where the NEXT append chains from (advanced by append, under the lock)
#   .verified.json  how far the chain has been re-walked and found intact (advanced by verify)
# Both are DERIVED caches, never the record: every consumer validates the triple against the
# stream's real byte length and falls back to reading the stream itself when it does not match.
# Neither is an external anchor -- an attacker who can rewrite the stream can rewrite these too.
_TAIL = "tail"
_VERIFIED = "verified"


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


def _sidecar_path(root: Path, name: str, kind: str) -> Path:
    return root / f"{name}.{kind}.json"


def _read_sidecar(root: Path, name: str, kind: str) -> Optional[dict]:
    """The sidecar triple, or None when it is absent, unreadable, or not the expected shape.
    NEVER RAISES: every caller's fallback is to read the stream itself, so an unusable sidecar
    must be indistinguishable from an absent one."""
    try:
        with open(_sidecar_path(root, name, kind), "r", encoding="utf-8") as fh:
            data = _json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    rows, head, nbytes = data.get("rows"), data.get("head_hash"), data.get("bytes")
    # bool is an int subclass; reject it explicitly rather than reading True as 1.
    if isinstance(rows, bool) or isinstance(nbytes, bool):
        return None
    if not isinstance(rows, int) or not isinstance(nbytes, int) or not isinstance(head, str):
        return None
    if rows < 0 or nbytes < 0:
        return None
    return {"rows": rows, "head_hash": head, "bytes": nbytes}


def _write_sidecar(root: Path, name: str, kind: str, *, rows: int, head_hash: str,
                   nbytes: int) -> None:
    """Replace the sidecar atomically (unique temp file in the same directory + `os.replace`),
    so a reader never sees a half-written triple and two concurrent writers cannot interleave.
    NEVER RAISES: a sidecar that fails to land only costs the next caller a full read."""
    fd = None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=str(root), prefix=f".{name}.{kind}.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fd = None                      # fdopen owns it now
            _json.dump({"rows": rows, "head_hash": head_hash, "bytes": nbytes}, fh)
        os.replace(tmp, _sidecar_path(root, name, kind))
        tmp = None
    except Exception:
        pass
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def append(row: dict, *, name: str = _DEFAULT_STREAM, root: Optional[Path] = None) -> dict:
    """Append one row, computing its chain link — never rewrites an existing row. Holds the
    stream's exclusive lock across tail-read + append so the chain can never fork. Returns the
    stored row with `prev_hash`/`row_hash` populated. `root` overrides env-var resolution (see
    `store_root`). `append_indexed` is the same write; it also returns the row's chain index."""
    stored, _index = append_indexed(row, name=name, root=root)
    return stored


def append_indexed(row: dict, *, name: str = _DEFAULT_STREAM,
                   root: Optional[Path] = None) -> tuple:
    """`append`, plus the 0-based CHAIN INDEX the written row occupies — the position a reader
    walking the stream's well-formed rows in order would find it at. Returned rather than
    re-derived: a caller that needs the index (claim_graph's projection) would otherwise have to
    re-read the whole stream to find the row it just wrote, which is O(stream) per append.

    The tail sidecar makes the common case O(1): when it matches the stream's current byte
    length it names both the hash to chain from and the index to use, so no row is read at all.
    Any mismatch — absent sidecar, unreadable sidecar, a crash between the row write and the
    sidecar write, an external append, a rewrite, a truncation — falls back to the full `read()`
    and chains from the last WELL-FORMED row, exactly as this function did before the sidecar
    existed. The fallback repairs nothing: `bytes` is recorded as the file's real length, so a
    corrupt tail keeps its bytes and this row goes after them, as always."""
    with _Locked(name, root=root):
        root_path = store_root(root=root)
        target = root_path / f"{name}.jsonl"
        try:
            size = os.path.getsize(target)
        except OSError:                    # absent or unstattable -> take the fallback path
            size = None
        tail = _read_sidecar(root_path, name, _TAIL)
        if tail is not None and size is not None and tail["bytes"] == size:
            prev_hash = tail["head_hash"]
            index = tail["rows"]
        else:
            existing = read(name=name, root=root)
            prev_hash = existing[-1].get("row_hash", "") if existing else ""
            index = len(existing)
        stored = dict(row)
        stored.setdefault("status", OPEN)
        stored["prev_hash"] = prev_hash
        stored.pop("row_hash", None)
        stored["row_hash"] = _row_hash(prev_hash, stored)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(_dumps(stored) + "\n")
            fh.flush()
            # the file's length as it ACTUALLY is, taken from the fd we just wrote through --
            # not len() of the line, which counts characters, not the utf-8 bytes on disk.
            try:
                written = os.fstat(fh.fileno()).st_size
            except OSError:
                written = None
        if written is not None:
            _write_sidecar(root_path, name, _TAIL, rows=index + 1,
                           head_hash=stored["row_hash"], nbytes=written)
    return stored, index


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


def _scan_extent(target: Path) -> Optional[tuple]:
    """(non-blank line count, the LAST such line's `row_hash`, byte length) for the stream as it
    is right now — a byte-level pass that hashes nothing and parses only the last line. Only
    meaningful as a checkpoint when a full `verify_chain` of the same file came back clean, which
    is what makes "non-blank line count" and "well-formed row count" the same number. None when
    the stream is unreadable or its last line is not a JSON object (in which case `verify_chain`
    is about to name a broken row anyway, so nothing gets checkpointed)."""
    if not target.exists():
        return None
    rows = 0
    last = b""
    size = 0
    try:
        with open(target, "rb") as fh:
            for raw in fh:
                size += len(raw)
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    return None
                if not text.strip():
                    continue
                rows += 1
                last = raw
    except OSError:
        return None
    head = ""
    if last:
        try:
            parsed = _json.loads(last.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(parsed, dict):
            return None
        head = str(parsed.get("row_hash", "") or "")
    return rows, head, size


def _last_line_before(target: Path, offset: int) -> Optional[bytes]:
    """The last non-blank line lying entirely within the stream's first `offset` bytes, read
    backwards in chunks so the cost is the length of that one line, not of the stream. None when
    there is none, the read fails, or a single line runs past the sanity bound."""
    chunk = 4096
    pos = offset
    tail = b""
    try:
        with open(target, "rb") as fh:
            while pos > 0:
                step = min(chunk, pos)
                pos -= step
                fh.seek(pos)
                tail = fh.read(step) + tail
                parts = tail.split(b"\n")
                # parts[0] is only a whole line once we have read back to the file's start.
                for candidate in reversed(parts if pos == 0 else parts[1:]):
                    if candidate.strip():
                        return candidate
                if len(tail) > (1 << 20):
                    return None
    except OSError:
        return None
    return None


def _checkpoint_resumable(target: Path, checkpoint: dict) -> bool:
    """Is it safe to trust `checkpoint` and verify only what follows it? Requires the stream to
    be at least `bytes` long (anything shorter is a truncation) AND the last row inside those
    bytes to still hash to `head_hash` (the cheap re-verify of the recorded head row). False
    sends the caller to a full walk, which is always correct and only ever slower."""
    try:
        if os.path.getsize(target) < checkpoint["bytes"]:
            return False
    except OSError:
        return False
    if checkpoint["rows"] == 0:
        # nothing verified yet: only a zero-length prefix with no head row is coherent.
        return checkpoint["bytes"] == 0 and checkpoint["head_hash"] == ""
    if checkpoint["bytes"] == 0:
        return False
    raw = _last_line_before(target, checkpoint["bytes"])
    if raw is None:
        return False
    try:
        row = _json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(row, dict) and row.get("row_hash") == checkpoint["head_hash"]


def _verify_suffix(target: Path, *, offset: int, index: int, prev_hash: str) -> tuple:
    """Walk the stream from byte `offset`, chaining from `prev_hash` and numbering from `index`,
    applying exactly `verify_chain`'s per-row checks. Returns
    (broken_at_or_None, rows, head_hash, bytes) where the last three describe the extent walked
    and are meaningful only when broken_at is None. Raises what `verify_chain` raises on the
    same input (a non-utf-8 byte), so the caller's fault handling is unchanged."""
    idx = index
    expected_prev = prev_hash
    consumed = offset
    with open(target, "rb") as fh:
        fh.seek(offset)
        for raw in fh:
            consumed += len(raw)
            stripped = raw.decode("utf-8").strip()
            if not stripped:
                continue
            try:
                row = _json.loads(stripped)
            except ValueError:
                return idx, 0, "", 0
            if not isinstance(row, dict):
                return idx, 0, "", 0
            if row.get("prev_hash", "") != expected_prev:
                return idx, 0, "", 0
            if row.get("row_hash") != _row_hash(expected_prev, row):
                return idx, 0, "", 0
            expected_prev = row.get("row_hash", "")
            idx += 1
    return None, idx, expected_prev, consumed


def verify_chain_checkpointed(*, name: str = _DEFAULT_STREAM,
                              root: Optional[Path] = None) -> Optional[int]:
    """`verify_chain` — same full walk, same return contract — that ALSO records how far it got,
    so a later `verify_chain_incremental` can start there. The extent is measured BEFORE the walk
    on purpose: under a concurrent append the checkpoint then names a prefix the walk definitely
    covered, never bytes the walk never saw."""
    root_path = store_root(root=root)
    target = root_path / f"{name}.jsonl"
    extent = _scan_extent(target)
    broken_at = verify_chain(name=name, root=root)
    if broken_at is None and extent is not None:
        rows, head, nbytes = extent
        _write_sidecar(root_path, name, _VERIFIED, rows=rows, head_hash=head, nbytes=nbytes)
    return broken_at


def verify_chain_incremental(*, name: str = _DEFAULT_STREAM,
                             root: Optional[Path] = None) -> Optional[int]:
    """Verify only what has been appended since the last checkpoint. Same return contract as
    `verify_chain`: None when clean, else the 0-based index of the first bad row, counted from
    the start of the stream. Falls back to the full `verify_chain_checkpointed` walk whenever the
    checkpoint cannot be trusted — absent, unreadable, longer than the stream (a truncation), or
    naming a head row that no longer hashes to what was recorded.

    WHAT THIS DOES NOT DETECT. A BYTE-LENGTH-PRESERVING edit to a row before the checkpoint is
    invisible here until the next full walk. An edit that changes the byte length is caught, but
    incidentally rather than by design: it shifts every later byte, so the line ending at the
    recorded offset is no longer the recorded head row and the checkpoint is refused. And an
    actor who can rewrite the stream can rewrite `<name>.verified.json` too — neither file is
    anchored anywhere outside this directory — so the incremental pass narrows a tamper's
    detection window, it does not close it. The full walk is what closes it."""
    root_path = store_root(root=root)
    target = root_path / f"{name}.jsonl"
    if not target.exists():
        return None
    checkpoint = _read_sidecar(root_path, name, _VERIFIED)
    if checkpoint is not None and _checkpoint_resumable(target, checkpoint):
        try:
            broken_at, rows, head, nbytes = _verify_suffix(
                target, offset=checkpoint["bytes"], index=checkpoint["rows"],
                prev_hash=checkpoint["head_hash"])
        except OSError:
            return None                    # unreadable store reads as clean (verify_chain's contract)
        if broken_at is not None:
            return broken_at
        _write_sidecar(root_path, name, _VERIFIED, rows=rows, head_hash=head, nbytes=nbytes)
        return None
    return verify_chain_checkpointed(name=name, root=root)
