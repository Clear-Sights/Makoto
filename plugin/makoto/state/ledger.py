"""Results ledger: record `update`s and read them back by key.

An `update` records a result-producing operation's outcome, keyed by the
normalized location it concerns; latest-wins (a retest supersedes, never fires).
Reuses the verified real-payload extractor `lib.io.bash_output_text` so we
read the fields the live hook actually emits — never a hand-built shape.

Pure data layer: callers pass an open sqlite3 connection whose `ledger` table
matches db.py's schema (key, value, kind, exit, source_event_id, session_id, ts).
"""
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# The exclusive lock below is the chain's one concurrency guard, and `fcntl` does not exist on
# Windows. Imported unconditionally it raised ModuleNotFoundError out of every ledger update, and
# dispatch's deliberate fail-open then let EVERY call through unchecked -- total loss of coverage
# on one OS, announced only as a fault notice. Windows' own exclusive-region lock is `msvcrt`.
try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows, and by the injection test
    fcntl = None
    import msvcrt
else:
    msvcrt = None

from makoto.checks import normalize_path
from makoto.kit import bash_output_text, decode_history_event, is_test_runner
from makoto.substrate._canonAtoms import _row_ts
from makoto.state.store import _state_dir as _chain_state_dir

_PATH_IN_CMD_RX = re.compile(
    r"(?<![=\w.\-])(?P<path>`?(?:/[\w.\-]+)+/[\w.\-]+\.\w+|[\w.\-]+/[\w.\-]+\.\w+|[\w.\-]+\.\w+`?)"
)


def _bash_key(ev: dict) -> str:
    """Best-effort location a Bash run concerns: a path-shaped token in the
    command, else the cwd, else a stable 'bash' fallback (stated, not inferred)."""
    cmd = ev.get("tool_input", {}).get("command", "") or ""
    m = _PATH_IN_CMD_RX.search(cmd)
    if m:
        return normalize_path(m.group("path").strip("`"))
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
    tool_input = ev.get("tool_input", {})
    if tool in ("Write", "Edit", "MultiEdit"):
        key = normalize_path(tool_input.get("file_path", ""))
        if not key:
            return
        # §7.1 content-depth: a Write states the file's FULL content, so record its stripped
        # length ("0" == a zero-byte production) — the completion gate reads this to tell a
        # real "I produced X" from a hollow one. Edit/MultiEdit only PATCH existing content
        # (the file is not zero-byte just because a patch is small), so they stay value=None.
        value = None
        if tool == "Write":
            content = tool_input.get("content", "")
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
        cmd = tool_input.get("command", "") or ""
        kind, value = ("testrun", text[-500:]) if is_test_runner(cmd) else ("value", text[:500])
        _upsert(conn, _bash_key(ev), kind, value, exit_code, event_id, session_id, root=root)


def _upsert(conn, key, kind, value, exit_code, event_id, session_id, *, root=None) -> None:
    # The DO UPDATE carries a guard: a plain kind='value' Bash row must NOT overwrite a
    # kind='testrun' row sharing its key. `pytest` in /repo files the failure tail under
    # (key='/repo', kind='testrun'); the very next pathless `git status` upserts the SAME
    # primary key as kind='value', silently destroying the recorded failure — green_claim_gate
    # then reads latest_testrun()=='' and goes inert, absence reading as green. A later
    # testrun still supersedes a testrun (latest-wins for a retest is unchanged), and a
    # value row still supersedes a value row; the chain append below preserves every
    # pre-upsert row either way.
    conn.execute(
        "INSERT INTO ledger (key, value, kind, exit, source_event_id, session_id, ts) "
        "VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, kind=excluded.kind, "
        "exit=excluded.exit, source_event_id=excluded.source_event_id, "
        "session_id=excluded.session_id, ts=excluded.ts "
        "WHERE NOT (ledger.kind = 'testrun' AND excluded.kind = 'value')",
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


def latest_testrun_exit(conn, session_id: str) -> "int | None":
    """The EXIT STATUS of the same row `latest_testrun` returns, or None if unrecorded.

    Same table, same `kind='testrun'`, same `ORDER BY source_event_id DESC, rowid DESC` -- it must
    be the same row or the pair lies, so the ordering is written identically here rather than
    approximated. (One query returning both would be better still; it is kept separate only
    because `latest_testrun`'s `-> str` contract is read by several callers.)

    WHY THIS EXISTS. `green_claim_gate` decided a green claim by scanning the recorded 500-char
    OUTPUT TAIL for a failure token, and its own docstring recorded the consequence: a run that
    really was red but whose tail holds no recognized token -- a 'Killed' timeout, a bare
    collection abort, a coverage footer that pushed the summary out of the tail -- read as green.
    Detecting the PRESENCE of failure means absence is success by default.

    The status was on that row the whole time. A number does not have a vocabulary, cannot be
    paraphrased, and is not defeated by a tail that got truncated."""
    try:
        r = conn.execute(
            "SELECT exit FROM ledger WHERE session_id = ? AND kind = 'testrun' "
            "ORDER BY source_event_id DESC, rowid DESC LIMIT 1", [session_id]).fetchone()
    except Exception:
        return None
    if not r or r[0] is None:
        return None
    try:
        return int(r[0])
    except (TypeError, ValueError):
        return None


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
_DEFAULT_STREAM = "chain"
OPEN = "open"


def _dumps(row: dict) -> str:
    """The one byte-stable JSON line every write shares: sorted keys, unicode kept, compact."""
    return json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical(row: dict) -> str:
    """The chain's hash input: the row's structural fields EXCLUDING `row_hash` (a row cannot hash
    its own hash), `prev_hash` INCLUDED so the link binds to chain position. Sorted-key bytes."""
    return _dumps({k: v for k, v in row.items() if k != "row_hash"})


def _row_hash(prev_hash: str, row: dict) -> str:
    """sha256 of the EXACT link bytes (prev_hash + canonical): the chain hash must bind
    byte-for-byte, so it must NOT normalize whitespace first.

    The rejected construction hashed a per-line-rstripped copy built with
    str.splitlines(). splitlines()
    also breaks on U+2028/U+2029/U+0085 — characters `_dumps` emits literally
    (ensure_ascii=False) and which are agent-controlled (record_update chain-appends Bash
    stdout as `value`) — so two DISTINCT rows ("ok \u2028next" vs "ok\u2028next") produced
    the identical row_hash and verify_chain certified a swapped/edited row. For every row free
    of those separators this digest is byte-identical to the old one (canonical JSON can carry
    no raw \n and never ends in whitespace), so existing chains and the CHAIN-FORMAT v1
    vectors verify unchanged. The normalizing helper itself is gone: it had no caller
    left, and a hashing footgun with no user is a trap set for the next reader."""
    return hashlib.sha256((prev_hash + canonical(row)).encode("utf-8")).hexdigest()


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


# Windows' `msvcrt.locking` has no blocking-forever mode: `LK_LOCK` retries for ten seconds and
# then raises, so the wait is bounded either way. Polling `LK_NBLCK` keeps that bound explicit and
# owned here rather than inherited from the C runtime.
_LOCK_TIMEOUT_S = 10.0
_LOCK_POLL_S = 0.01


def _lock_exclusive(fh) -> None:
    """Take the exclusive lock on `fh`, blocking until it is ours.

    Both backends lock the WHOLE-FILE region every other process locks: flock is inherently
    whole-file, and the msvcrt path seeks to 0 and locks one byte, so every waiter contends over
    byte 0 of the same sidecar. Locking at the current position instead would let two appenders
    hold disjoint regions and fork the chain -- the exact failure this lock exists to prevent.
    """
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        return
    fh.seek(0)
    deadline = time.monotonic() + _LOCK_TIMEOUT_S
    while True:
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(_LOCK_POLL_S)


def _unlock(fh) -> None:
    """Release before close. flock releases on close by itself; msvcrt must be told, and an
    already-released region raises OSError, which is the state we wanted anyway."""
    if fcntl is not None:
        return
    fh.seek(0)
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


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
        _lock_exclusive(self._fh)
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            _unlock(self._fh)
            self._fh.close()
            self._fh = None


def read(*, name: str = _DEFAULT_STREAM, root: Optional[Path] = None) -> list:
    """The named stream as an ordered list of row dicts. `[]` when absent (presence-detection).
    A truncated/corrupt/undecodable tail ends the read at that point — the well-formed PREFIX
    is returned, never a raised parse error. Reads BYTES and decodes per line: a single
    non-UTF-8 byte anywhere in the file must degrade to the same corrupt-tail behavior, not
    raise UnicodeDecodeError out of every chain reader forever. Does NOT verify the chain
    (that is `verify_chain`)."""
    target = store_root(root=root) / f"{name}.jsonl"
    try:
        raw = target.read_bytes()
    except OSError:
        return []
    rows = []
    for raw_line in raw.split(b"\n"):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except ValueError:      # includes UnicodeDecodeError on a non-UTF-8 line
            break
    return rows


def _repair_torn_tail(target: Path) -> None:
    """If the stream's final line is a PARTIAL write (no trailing newline — a tear from
    ENOSPC/EDQUOT during flush, or a kill mid-write), finish or drop it under the caller's
    lock BEFORE the next append: otherwise `append` opens in "a" and glues its row onto the
    fragment, every chain reader is blind past the tear forever, and `append` keeps returning
    populated rows as though recorded. A complete row merely missing its newline is completed;
    an unparseable fragment is truncated away — that row never fully existed and its own
    append already raised at tear time. A corrupt line WITH its newline intact is left
    untouched: that is tamper territory, verify_chain's job to name, never silently rewritten."""
    try:
        with open(target, "rb+") as fh:
            data = fh.read()
            if not data or data.endswith(b"\n"):
                return
            tail = data.rsplit(b"\n", 1)[-1]
            try:
                json.loads(tail)
            except ValueError:
                fh.truncate(len(data) - len(tail))   # drop the torn fragment
                return
            fh.write(b"\n")                          # complete the un-newlined full row
    except OSError:
        return


def append(row: dict, *, name: str = _DEFAULT_STREAM, root: Optional[Path] = None) -> dict:
    """Append one row, computing its chain link — never rewrites an existing row. Holds the
    stream's exclusive lock across tail-read + append so the chain can never fork. Returns the
    stored row with `prev_hash`/`row_hash` populated. `root` overrides env-var resolution (see
    `store_root`)."""
    with _Locked(name, root=root):
        _repair_torn_tail(store_root(root=root) / f"{name}.jsonl")
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
    RAISES: an unreadable store reads as None, and a NON-UTF-8 line is a broken row (its
    index is returned) rather than a raised UnicodeDecodeError — the bytes are read raw and
    decoded per line for exactly that reason. `root` overrides env-var resolution (see
    `store_root`) -- a caller verifying a chain it appended via an explicit root must pass the
    SAME root here, or it will resolve the wrong stream."""
    target = store_root(root=root) / f"{name}.jsonl"
    if not target.exists():
        return None
    try:
        raw = target.read_bytes()
    except OSError:
        return None
    expected_prev = ""
    idx = 0
    for raw_line in raw.split(b"\n"):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except ValueError:      # unparseable OR undecodable line -> the exact broken row
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
# Host-written operator turns and call-window boundaries.
_SYNTHETIC_MARKERS = (
    "<system-reminder", "<user-prompt-submit-hook", "<task-notification",
    "<local-command-caveat", "[request interrupted by user]",
)

_MIDTURN_MESSAGE_RX = re.compile(
    r"\A<system-reminder>\s*The user sent a new message while you were working:\s*\n"
    r"(?P<prompt>.*?)\s*</system-reminder>\Z", re.DOTALL)


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
    """Return the entry's text iff it is a genuine, host-written, non-synthetic user turn -- else None. A tool result or a synthetic/system-injected turn can
    never qualify, no matter what text it happens to contain."""
    # Claude records queued prompts as their own attachment, even when the rendered message
    # appears beside tool output (anthropics/claude-code#49625, captured 2.1.112 transcript).
    attachment = entry.get("attachment")
    if (entry.get("type") == "attachment" and entry.get("userType") == "external"
            and isinstance(attachment, dict) and attachment.get("type") == "queued_command"
            and attachment.get("commandMode") == "prompt" and "toolUseResult" not in entry):
        prompt = attachment.get("prompt")
        return prompt if isinstance(prompt, str) else None
    msg = entry.get("message")
    if not isinstance(msg, dict) or msg.get("role") != "user":
        return None
    # A mid-turn prompt may instead be a separate host text block in a user envelope that
    # ALSO carries toolUseResult. Match that complete block, never a substring, tool_result
    # content, stdout, or another synthetic reminder. Tool-returned copies cannot qualify.
    content = msg.get("content")
    if isinstance(content, list):
        prompts = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            value = block.get("text")
            match = _MIDTURN_MESSAGE_RX.fullmatch(value.strip()) if isinstance(value, str) else None
            if match and match["prompt"].strip():
                prompts.append(match["prompt"].strip())
        if prompts:
            return "\n".join(prompts)
    if ("toolUseResult" in entry or (isinstance(content, list) and any(
            isinstance(block, dict) and block.get("type") == "tool_result" for block in content))):
        return None
    text = _entry_text(entry)
    low = text.lower()
    if any(marker in low for marker in _SYNTHETIC_MARKERS):
        return None
    return text


def _genuine_user_turns(transcript_path: Optional[str], *, limit: int = 4000) -> list:
    """Every genuine, host-written, non-synthetic user turn as (text, timestamp), oldest first.

    Shared provenance reader for checks that distinguish operator input from tool output.

    Never raises: an absent, unreadable or malformed transcript reads as "no user turns". Callers
    must treat that as absence of evidence, never as evidence of absence.

    `limit` bounds the scan; a transcript is unbounded in principle and this runs on a hot path.
    """
    turns = []
    for entry in _transcript_entries(transcript_path, limit=limit):
        text = _is_genuine_user_turn(entry)
        if text:
            turns.append((text, entry.get("timestamp")))
    return turns


def _transcript_entries(transcript_path: Optional[str], *, limit: int | None, newest=False) -> list:
    """Read host records from the head or tail; limit=None reads all records."""
    if not transcript_path:
        return []
    p = Path(transcript_path)
    try:
        if not p.exists():
            return []
        # "utf-8-sig", not "utf-8": a transcript written by a host that prefixes a UTF-8 BOM
        # decoded with a leading U+FEFF glued onto the FIRST record, so that record alone failed
        # to parse and every user turn in it vanished. The first record is where a session's
        # opening message lives -- routinely the turn carrying the URL the user typed -- and its
        # loss lands in `_user_supplied` as "the user never typed it", i.e. the same deny resting
        # on a false fact that the `splitlines` note below is about. "utf-8-sig" strips the BOM
        # when present and is byte-for-byte the same decode when it is not.
        raw = p.read_text(encoding="utf-8-sig", errors="replace")
    except (OSError, ValueError):
        return []
    entries = []
    # `splitlines()`, NOT iteration over the file handle, and the difference is a live false deny.
    #
    # This was briefly rewritten to `islice` over an open handle, to apply the `limit` bound before
    # paying for every byte rather than after. That bound is a real concern and the rewrite was
    # wrong anyway: file iteration splits ONLY on \n, while `splitlines()` also splits on \v, \f,
    # \x1c-\x1e, \x85, U+2028 and U+2029. A transcript carrying any of those collapsed into one
    # unparseable line and this function returned [] -- measured, all five separators tested.
    #
    # [] here does not read as "no evidence". It flows into `_user_supplied`, which reports that the
    # user never typed the URL, and `content.unsourced_webfetch` DENIES with exactly that as its
    # stated reason. So the optimization turned an ordinary WebFetch of a URL the user had typed
    # into a hard deny resting on a false fact -- the one thing a gate must never do. Correctness
    # first: if the unbounded read has to go, it needs a form that splits on the same set.
    lines = raw.splitlines()
    for line in (lines[-limit:] if newest and limit is not None and limit > 0 else lines[:limit]):
        # `strip("\ufeff")` as well as whitespace. "utf-8-sig" removes a BOM only at BYTE ZERO, so
        # a transcript that is the concatenation of separately-written chunks -- which is how a
        # resumed or merged session is produced -- keeps a U+FEFF glued to the front of every
        # chunk after the first. `json.loads` rejects each of those records, and every user turn
        # in them disappears; the loss lands in `_user_supplied` as "the user never typed it",
        # which is a hard deny resting on a false fact. Stripping per record costs nothing and
        # makes the reader indifferent to where the chunk boundaries fell.
        line = line.strip().strip("\ufeff").strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        entries.append(entry)
    return entries


def user_turn_texts(transcript_path: Optional[str], *, limit: int = 4000) -> list:
    """Every genuine user turn's TEXT, oldest first. See `_genuine_user_turns` for the reader."""
    return [text for text, _ in _genuine_user_turns(transcript_path, limit=limit)]


def last_operator_turn_ts(transcript_path: Optional[str], *, limit: int = 4000) -> Optional[str]:
    """The latest genuine operator message or exact host interruption marker timestamp.

    An exact host interrupt also closes the window, but never enters the user-prose
    channel used for consent or URLs. None means no established operator boundary.
    """
    for entry in reversed(_transcript_entries(transcript_path, limit=limit, newest=True)):
        ts = entry.get("timestamp")
        msg = entry.get("message")
        # This exact host event closes a turn but says nothing about approval or URLs.
        # Keep it out of _is_genuine_user_turn / user_turn_texts for every prose consumer.
        interrupt = (entry.get("type") == "user" and isinstance(msg, dict)
                     and msg.get("role") == "user" and "toolUseResult" not in entry
                     and _entry_text(entry).strip() == "[Request interrupted by user]"
                     and not (isinstance(msg.get("content"), list) and any(
                         isinstance(b, dict) and b.get("type") == "tool_result"
                         for b in msg["content"])))
        if ts and (_is_genuine_user_turn(entry) or interrupt):
            return str(ts)
    return None


def _event_instant(value):
    """An aware event timestamp, or None when the record cannot establish an instant."""
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def operator_window(history, transcript_path: Optional[str]) -> list:
    """Raw events in the current operator window, shared by the two blocking Canon gates.

    Claude's PostToolUseFailure.is_interrupt explicitly denotes a USER interruption:
    https://code.claude.com/docs/en/hooks#posttoolusefailure-input. It closes the window
    through that terminal, even without a transcript. Bash tool_response.interrupted also
    means timeout/abort and must NOT be interpreted as operator intent. No tool text is read.
    Unknown timestamps are retained; timestamp formats are compared as instants, not strings.
    """
    since = _event_instant(last_operator_turn_ts(transcript_path))
    rows = list(history or ())
    start = 0
    for index, row in enumerate(rows):
        event = decode_history_event(row)
        if (isinstance(event, dict) and event.get("hook_event_name") == "PostToolUseFailure"
                and event.get("is_interrupt") is True):
            start = index + 1
    return [row for row in rows[start:]
            if since is None or (ts := _event_instant(_row_ts(row))) is None or ts >= since]


def last_fired_ts(fingerprint_id: str, *, gate_pattern_id: str = "gate.canon_fingerprints",
                  session_id: Optional[str] = None,
                  root: Optional[Path] = None) -> Optional[str]:
    """Latest timestamp of a chain-recorded audit firing naming this fingerprint and session."""
    needle = f"canon.{fingerprint_id}:"
    latest = None
    latest_instant = None
    for row in read(root=root):
        if row.get("kind") != "audit" or row.get("session_id") != session_id:
            continue
        if gate_pattern_id not in (row.get("pattern_fires") or []):
            continue
        if not any(needle in (finding.get("message") or "")
                   for finding in row.get("findings") or ()):
            continue
        instant = _event_instant(row.get("ts"))
        if instant is not None and (latest_instant is None or instant > latest_instant):
            latest, latest_instant = row["ts"], instant
    return latest


# =============================================================================================
# receipt (merged from record/receipt.py -- Stage 2 seam 1)
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
