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
from makoto.lib.io import bash_output_text, is_test_runner

_PATH_IN_CMD_RX = re.compile(r"[\w.\-]+/[\w.\-]+\.\w+|`?([\w.\-]+\.\w+)`?")


def _bash_key(ev: dict) -> str:
    """Best-effort location a Bash run concerns: a path-shaped token in the
    command, else the cwd, else a stable 'bash' fallback (stated, not inferred)."""
    cmd = ev.get("tool_input", {}).get("command", "") or ""
    m = _PATH_IN_CMD_RX.search(cmd)
    if m:
        return normalize_path(m.group(0))
    return normalize_path(ev.get("cwd", "")) or "bash"


def record_update(conn, ev: dict, *, event_id: int, session_id: str) -> None:
    """Record one update from a PostToolUse event. Write/Edit -> a `touched` row;
    Bash -> a `value` row with extracted output + exit code. Latest-wins."""
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
        _upsert(conn, key, "touched", value, None, event_id, session_id)
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
            _upsert(conn, _bash_key(ev), "testrun", text[-500:], exit_code, event_id, session_id)
        else:
            _upsert(conn, _bash_key(ev), "value", text[:500], exit_code, event_id, session_id)


def _upsert(conn, key, kind, value, exit_code, event_id, session_id) -> None:
    conn.execute(
        "INSERT INTO ledger (key, value, kind, exit, source_event_id, session_id, ts) "
        "VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, kind=excluded.kind, "
        "exit=excluded.exit, source_event_id=excluded.source_event_id, ts=excluded.ts",
        [key, value, kind, exit_code, event_id, session_id],
    )
    conn.commit()


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
