"""#19 (camelCase host dialects): the host-dialect boundary (makoto.core.hostdialect).

A Cursor-style host loads Claude-Code-compatible hook wiring but delivers the event name in
camelCase (`preToolUse`, `postToolUse`). Before the boundary existed, dispatch routed on the
exact spelling: a `postToolUse` event fell through the HANDLERS wildcard to the WRONG handler
(_evaluate_and_gate instead of _accumulate), and the events table persisted the host's own
spelling — leaving every history decoder that keys on `hook_event_name == "PreToolUse"/
"PostToolUse"` (canon.timeout/canon.recur, gate.identical_retry, the claim-graph Bash-evidence
path) silently blind for the whole session.

Reproduction discipline: `test_dispatch_persists_canonical_event_for_camelcase_host` was run
against the unfixed tree and failed (row persisted as `preToolUse`); it passes with the boundary
in place. The unevaluable-envelope refusals (non-object payload) are pinned unchanged.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from makoto.core import hostdialect
from makoto.dispatch import HANDLERS


def _setup_state(tmp_path):
    from makoto.state.store import init_db
    state_dir = tmp_path / "makoto_state"
    citations = tmp_path / "CITATIONS.md"
    citations.write_text("Smith 2020\n")
    init_db(state_dir, citations)
    return state_dir


def _run_dispatch(state_dir, payload) -> tuple[int, str]:
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto.dispatch"],
        input=(payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")),
        capture_output=True, env=env, cwd=str(Path(__file__).parent.parent),
    )
    return proc.returncode, proc.stdout.decode("utf-8")


def _events(state_dir):
    import sqlite3
    conn = sqlite3.connect(str(Path(state_dir) / "makoto.record.db"))
    try:
        return conn.execute("SELECT event_type, payload FROM events ORDER BY id").fetchall()
    finally:
        conn.close()


# ---- the pure boundary -----------------------------------------------------------------------
def test_canonical_event_folds_camelcase_to_known_name():
    assert hostdialect.canonical_event("preToolUse", HANDLERS) == "PreToolUse"
    assert hostdialect.canonical_event("postToolUse", HANDLERS) == "PostToolUse"
    assert hostdialect.canonical_event("stop", HANDLERS) == "Stop"


def test_canonical_event_exact_match_wins_and_unknown_stays_none():
    assert hostdialect.canonical_event("PreToolUse", HANDLERS) == "PreToolUse"
    assert hostdialect.canonical_event("beforeShellExecution", HANDLERS) is None
    assert hostdialect.canonical_event(None, HANDLERS) is None
    assert hostdialect.canonical_event(42, HANDLERS) is None


def test_alias_index_is_derived_and_refuses_case_collisions():
    idx = hostdialect.alias_index({"PreToolUse", "pretooluse"})
    assert "pretooluse" not in idx  # ambiguous fold refused; exact match still decides
    idx2 = hostdialect.alias_index({"PreToolUse", "Stop"})
    assert idx2 == {"pretooluse": "PreToolUse", "stop": "Stop"}


def test_normalize_payload_fills_protocol_fields_only_when_absent():
    out, notes = hostdialect.normalize_payload(
        {"hook_event_name": "preToolUse", "conversation_id": "c1",
         "tool_name": "Shell", "tool_input": {"command": "ls"}},
        HANDLERS)
    assert out["hook_event_name"] == "PreToolUse"
    assert out["session_id"] == "c1"
    assert out["tool_name"] == "Bash"
    assert notes == {"hook_event_name": "preToolUse", "session_id": "conversation_id",
                     "tool_name": "Shell"}
    # a host already speaking the protocol: untouched, empty notes
    proto = {"hook_event_name": "PreToolUse", "session_id": "s",
             "tool_name": "Bash", "tool_input": {"command": "ls"}}
    out2, notes2 = hostdialect.normalize_payload(proto, HANDLERS)
    assert out2 == proto and notes2 == {}


def test_normalize_payload_never_aliases_shell_without_command_evidence():
    out, notes = hostdialect.normalize_payload(
        {"hook_event_name": "PreToolUse", "session_id": "s",
         "tool_name": "Shell", "tool_input": {"something_else": 1}}, HANDLERS)
    assert out["tool_name"] == "Shell" and "tool_name" not in notes


def test_normalize_payload_decodes_string_tool_output_and_wraps_scalars():
    out, _ = hostdialect.normalize_payload(
        {"hook_event_name": "postToolUse", "session_id": "s", "tool_name": "Bash",
         "tool_input": {"command": "x"}, "tool_output": json.dumps({"stdout": "hi"})}, HANDLERS)
    assert out["tool_response"] == {"stdout": "hi"}
    out2, _ = hostdialect.normalize_payload(
        {"hook_event_name": "postToolUse", "session_id": "s", "tool_name": "Bash",
         "tool_input": {"command": "x"}, "tool_output": "plain text"}, HANDLERS)
    assert out2["tool_response"] == {"output": "plain text"}


def test_normalize_payload_never_synthesizes_last_assistant_message():
    out, _ = hostdialect.normalize_payload(
        {"hook_event_name": "stop", "session_id": "s"}, HANDLERS)
    assert "last_assistant_message" not in out


def test_normalize_payload_copy_is_deep_on_nested_tool_dicts():
    src = {"hook_event_name": "PreToolUse", "session_id": "s",
           "tool_name": "Bash", "tool_input": {"command": "x"}}
    out, _ = hostdialect.normalize_payload(src, HANDLERS)
    assert out["tool_input"] == src["tool_input"]
    assert out["tool_input"] is not src["tool_input"]


# ---- dispatch integration: the reproduction of #19's downstream blindness --------------------
def test_dispatch_persists_canonical_event_for_camelcase_host(tmp_path):
    """THE #19 reproduction: a camelCase envelope must be persisted (wrapper event_type AND
    payload hook_event_name) in the protocol spelling, so history decoders keying on
    `== "PreToolUse"/"PostToolUse"` are not blind to the whole session."""
    state_dir = _setup_state(tmp_path)
    rc, _ = _run_dispatch(state_dir, {
        "hook_event_name": "preToolUse", "session_id": "c1", "cwd": "/tmp",
        "tool_name": "Bash", "tool_input": {"command": "echo hi"}})
    assert rc == 0
    rows = _events(state_dir)
    assert len(rows) == 1
    etype, payload_raw = rows[0]
    assert etype == "PreToolUse", f"wrapper event_type persisted as {etype!r}"
    assert json.loads(payload_raw)["hook_event_name"] == "PreToolUse"


def test_dispatch_protocol_host_ingests_its_own_bytes(tmp_path):
    """A protocol-speaking host's raw payload is persisted byte-identical (no rewrite)."""
    state_dir = _setup_state(tmp_path)
    payload = {"hook_event_name": "PreToolUse", "session_id": "s1", "cwd": "/tmp",
               "tool_name": "Bash", "tool_input": {"command": "echo hi"}}
    raw = json.dumps(payload)
    rc, _ = _run_dispatch(state_dir, raw.encode("utf-8"))
    assert rc == 0
    assert _events(state_dir)[0][1] == raw


def test_dispatch_rewritten_payload_raw_keeps_non_ascii_unescaped(tmp_path):
    """8fec86e regression pin: the normalized persisted row must not \\uXXXX-escape non-ASCII —
    the Pre-tier keyword prefilter reads it as a raw substring."""
    state_dir = _setup_state(tmp_path)
    rc, _ = _run_dispatch(state_dir, {
        "hook_event_name": "preToolUse", "session_id": "s1", "cwd": "/tmp",
        "tool_name": "Bash", "tool_input": {"command": "echo héllo"}})
    assert rc == 0
    assert "héllo" in _events(state_dir)[0][1]


def test_dispatch_non_object_payload_still_fails_closed(tmp_path):
    """The tamper path is NOT relaxed: valid-JSON-non-object still blocks (exit 2)."""
    state_dir = _setup_state(tmp_path)
    rc, _ = _run_dispatch(state_dir, b'["not", "an", "object"]')
    assert rc == 2


def test_dispatch_notes_dialect_once_per_session(tmp_path):
    state_dir = _setup_state(tmp_path)
    for _ in range(2):
        rc, _ = _run_dispatch(state_dir, {
            "hook_event_name": "preToolUse", "session_id": "c9", "cwd": "/tmp",
            "tool_name": "Bash", "tool_input": {"command": "echo hi"}})
        assert rc == 0
    markers = list((Path(state_dir) / "host_dialect").glob("*.json"))
    assert len(markers) == 1
    facts = (Path(state_dir) / "dispatch_errors.jsonl")
    n = sum(1 for ln in facts.read_text().splitlines()
            if "host_dialect" in ln) if facts.exists() else 0
    assert n == 1, f"dialect noted {n} times; must be once per session"
