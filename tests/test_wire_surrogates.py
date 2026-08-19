"""The byte boundary: a host byte that is not valid UTF-8 must never skip a check.

REGRESSION ORIGIN (live, measured). `dispatch.main()` opened with `sys.stdin.read()`. A hook
subprocess inherits no LANG, so CPython enables UTF-8 mode and gives stdin the `surrogateescape`
error handler; a byte the host wrote that is not valid UTF-8 therefore entered as a LONE SURROGATE
rather than raising or being replaced. It survived `json.loads`, reached `_ingest_event`, and died
there, because sqlite3 encodes bind parameters strictly::

    UnicodeEncodeError: 'utf-8' codec can't encode character '\\udc9d'
                        in position 143: surrogates not allowed

`\\udc9d` is `0xDC00 + 0x9D` -- the surrogateescape of byte 0x9D. `main()`'s catch-all then wrote a
`loud-allow` fact and exited 0, so the tool call PROCEEDED WITH NO CHECK HAVING RUN. 30 of these in
one day, all of them Makoto failing open on its own bug.

The tests below pin the exact reproducer bytes, not a paraphrase of them.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

from tests.conftest import _setup_state

REPO_ROOT = Path(__file__).parent.parent

# The literal live crash envelope. 0x9D is raw, unescaped, and invalid UTF-8 exactly as the host
# delivered it. Byte-level, because the whole defect lived below the character level: a test that
# built this payload with json.dumps could not reproduce it at all.
CRASH_BYTES = (
    b'{"hook_event_name":"PreToolUse","tool_name":"Write","session_id":"s-crash",'
    b'"cwd":"/tmp","tool_input":{"file_path":"/tmp/x.py","content":"hello \x9d world"}}'
)


def _run_bytes(state_dir, raw: bytes) -> tuple[int, str, str]:
    """Run the real dispatcher with RAW BYTES on stdin. Returns (exit, stdout, stderr)."""
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    proc = subprocess.run([sys.executable, "-m", "makoto.dispatch"], input=raw,
                          capture_output=True, env=env, cwd=str(REPO_ROOT))
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8", "replace")


def _errors(state_dir) -> list:
    f = Path(state_dir) / "dispatch_errors.jsonl"
    if not f.exists():
        return []
    return [json.loads(ln) for ln in f.read_text().splitlines() if ln.strip()]


def test_undecodable_byte_no_longer_crashes_the_dispatcher(tmp_path):
    """The live reproducer: exit 0, and NOT ONE UnicodeEncodeError anywhere."""
    state_dir = _setup_state(tmp_path)
    code, _out, err = _run_bytes(state_dir, CRASH_BYTES)
    assert code == 0
    assert "UnicodeEncodeError" not in err
    assert not [r for r in _errors(state_dir) if "UnicodeEncodeError" in r.get("exc_message", "")]


def test_undecodable_byte_is_repaired_not_allowed_unchecked(tmp_path):
    """The substantive claim: the payload is REPAIRED and evaluation continues.

    A row saying `loud-allow` would mean the call went through unchecked, which is the defect. The
    disposition is the assertion -- exit 0 alone cannot tell the two apart.
    """
    state_dir = _setup_state(tmp_path)
    _run_bytes(state_dir, CRASH_BYTES)
    rows = [r for r in _errors(state_dir) if r["pattern_id"] == "dispatch.unencodable_input"]
    assert len(rows) == 1
    assert rows[0]["exc_message"].startswith("REPAIRED:")
    assert "loud-allow" not in rows[0]["exc_message"]


def test_repaired_event_still_reaches_the_predicates(tmp_path):
    """The point of repairing rather than bailing: the CHECK STILL RUNS on the repaired payload.

    Same undecodable byte, but the content now also carries a real violation. Before the fix this
    envelope died in `_ingest_event` and the fabricated-URL check never saw it.
    """
    state_dir = _setup_state(tmp_path)
    raw = (b'{"hook_event_name":"PreToolUse","tool_name":"WebFetch","session_id":"s-live",'
           b'"cwd":"/tmp","tool_input":{"url":"https://invented-host\x9d.example/v3/api"}}')
    code, out, _err = _run_bytes(state_dir, raw)
    assert code == 0
    assert "content.unsourced_webfetch" in out, "the check must fire on the repaired payload"


def test_unpaired_surrogate_escape_is_also_closed(tmp_path):
    """The OTHER door: valid UTF-8 bytes whose JSON text carries an unpaired \\uD8xx escape.

    `wire.read_stdin` cannot see this one -- the escape is plain ASCII in the raw text -- so it is
    `wire.scrub` on the parsed object that closes it. Both doors end at the same sqlite3 raise, so
    a fix for only one of them is not a fix.
    """
    state_dir = _setup_state(tmp_path)
    raw = (b'{"hook_event_name":"PreToolUse","tool_name":"Write","session_id":"s-esc",'
           b'"cwd":"/tmp","tool_input":{"file_path":"/tmp/y.py","content":"hi \\ud89d there"}}')
    code, _out, err = _run_bytes(state_dir, raw)
    assert code == 0
    assert "UnicodeEncodeError" not in err
    rows = [r for r in _errors(state_dir) if r["pattern_id"] == "dispatch.unencodable_input"]
    assert len(rows) == 1 and "1 unpaired surrogate escape" in rows[0]["exc_message"]


def test_legitimate_replacement_char_is_not_counted_as_damage(tmp_path):
    """A payload that genuinely contains U+FFFD is CLEAN and must produce no repair row.

    Decoding straight to errors="replace" and counting U+FFFD would report damage here forever. A
    repair count that cries wolf gets ignored, and the next real one goes with it.
    """
    state_dir = _setup_state(tmp_path)
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Write", "session_id": "s-fffd",
               "cwd": "/tmp", "tool_input": {"file_path": "/tmp/z.py", "content": "legit � char"}}
    code, _out, _err = _run_bytes(state_dir, json.dumps(payload).encode("utf-8"))
    assert code == 0
    assert [r for r in _errors(state_dir) if r["pattern_id"] == "dispatch.unencodable_input"] == []


def test_clean_payload_takes_the_strict_path_unchanged(tmp_path):
    """An ordinary envelope must be untouched: no repair row, no notice, empty wire."""
    state_dir = _setup_state(tmp_path)
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "s-ok",
               "cwd": "/tmp", "tool_input": {"file_path": "/tmp/a"}}
    code, out, _err = _run_bytes(state_dir, json.dumps(payload).encode("utf-8"))
    assert code == 0 and out == ""
    assert _errors(state_dir) == []


# --- unit-level guarantees of the boundary module itself ------------------------------------

def test_scrub_reports_what_it_replaced():
    from makoto.core import wire
    text, n = wire.scrub_text("a\ud89db\udc9dc")
    assert n == 2 and "\ud89d" not in text and "\udc9d" not in text


def test_scrub_walks_nested_containers_and_keys():
    from makoto.core import wire
    value, n = wire.scrub({"k\ud89d": ["a", {"deep": "v\udc9d"}]})
    assert n == 2
    assert json.dumps(value)  # the whole point: it now serializes


def test_scrub_returns_clean_input_untouched():
    from makoto.core import wire
    original = {"a": ["b", {"c": "d"}]}
    value, n = wire.scrub(original)
    assert n == 0 and value is original


# --- found by an independent review pass, not by the tests above ------------------------------
#
# Both of these survived the first fix. They are kept as named regressions because each marks a
# place where "we closed the boundary" was true and insufficient.

def test_host_dialect_normalization_cannot_reintroduce_a_surrogate(tmp_path):
    """THE THIRD DOOR. `hostdialect._tool_result` runs `json.loads` on Cursor's `tool_output`,
    which arrives as a JSON *string*. An unpaired `\\ud800` escape inside that inner document is
    plain ASCII in the outer payload, so neither the byte decode nor the post-parse scrub can see
    it -- normalization is what materializes it, and the `ensure_ascii=False` reserialization then
    carried it live into the sqlite3 bind.

    Reproduced the ORIGINAL UnicodeEncodeError on a camelCase envelope with the boundary fix
    already in place. A boundary is only a boundary if nothing downstream re-parses.
    """
    state_dir = _setup_state(tmp_path)
    payload = {"hook_event_name": "postToolUse", "tool_name": "Bash", "session_id": "s-cursor",
               "cwd": "/tmp", "tool_input": {"command": "echo hi"},
               "tool_output": '{"error":"\\ud800 boom"}'}
    code, _out, err = _run_bytes(state_dir, json.dumps(payload).encode("utf-8"))
    assert code == 0
    assert "UnicodeEncodeError" not in err
    rows = _errors(state_dir)
    assert not [r for r in rows if "UnicodeEncodeError" in r.get("exc_message", "")]
    repaired = [r for r in rows if r["pattern_id"] == "dispatch.unencodable_input"]
    assert repaired and "host-dialect normalization" in repaired[0]["exc_message"]


def test_repair_count_is_bytes_not_malformed_runs():
    """`errors="replace"` emits ONE U+FFFD per malformed RUN, so a truncated three-byte sequence
    (two undecodable bytes) reported 1 -- under a field named "bytes repaired". `surrogateescape`
    maps each bad BYTE to exactly one surrogate, so the count means what the field says."""
    from makoto.core import wire
    _text, n = wire._decode_counting(b"\xe2\x82")
    assert n == 2, "two undecodable bytes must count as two"
    _text, n = wire._decode_counting(b"x\x9dy")
    assert n == 1
    _text, n = wire._decode_counting("legit � char".encode("utf-8"))
    assert n == 0, "a genuine U+FFFD is not damage"


def test_two_damaged_keys_do_not_collapse_into_one_losing_a_value():
    """Scrubbing is not injective on keys: every surrogate becomes the same U+FFFD.

    Found by an independent review pass. `wire.scrub({"\\ud800": 1, "\\ud801": 2})` returned
    `({'\\ufffd': 2}, 2)` -- a repair count of 2 sitting next to a dict that had silently lost a
    field. This module's one promise is that repair is ON THE RECORD; deleting a field without a
    word is the opposite of that, and the field could have been `tool_input`.
    """
    from makoto.core import wire
    value, n = wire.scrub({"\ud800": 1, "\ud801": 2})
    assert n == 2
    assert sorted(value.values()) == [1, 2], f"a value was discarded: {value!r}"
    assert not any("\ud800" <= c <= "\udfff" for k in value for c in k)


def test_a_repaired_key_does_not_evict_a_clean_key_of_the_same_name():
    """The ordering case: the clean key keeps its own name, whichever side of the dict it is on."""
    from makoto.core import wire
    value, _n = wire.scrub({"\ud800": 1, "\ufffd": 2})
    assert sorted(value.values()) == [1, 2]
    assert value["\ufffd"] == 2
