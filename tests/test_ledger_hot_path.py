"""The hook hot path must not be O(chain size).

Before this, every hook invocation parsed the whole chain repeatedly: `ledger.append` read it
to find the last row's hash, `claim_graph._row_index` read it again to locate the row append had
just written, and `_dispatch._self_verify_chain` re-walked and re-hashed all of it. Measured on a
212k-row chain that was 2.6 s per PreToolUse and 18 s per PostToolUse.

Two sidecars replace the reads, and the tests below are about the two things that can go wrong
with a cache of a file: it can be WRONG (so every fallback path is exercised here, and the fast
path is checked against the answer a full read would have given), and it can silently stop being
used (so `test_hot_dispatch_never_parses_the_whole_chain` asserts STRUCTURALLY -- by spying on
`ledger.read` / `ledger.verify_chain` -- that the hot path calls neither, which is what a
wall-clock assertion would only imply, and would flake about on a loaded machine)."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from makoto.record import ledger


# --------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------

def _chain(root: Path) -> Path:
    return root / "chain.jsonl"


def _rows_on_disk(root: Path) -> list:
    return ledger.read(root=root)


def _index_by_reading(root: Path, row_hash: str):
    """The index the deleted `claim_graph._row_index` would have returned: the position of the
    row with this hash among the stream's well-formed rows. This is the ORACLE the O(1) index
    is checked against."""
    for index, row in enumerate(ledger.read(root=root)):
        if row.get("row_hash") == row_hash:
            return index
    return None


def _tamper_field(root: Path, line_no: int, key: str = "k", value: str = "TAMPERED") -> None:
    """Hand-edit one row's field, leaving its now-stale row_hash in place."""
    path = _chain(root)
    lines = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[line_no])
    row[key] = value
    lines[line_no] = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------------
# A. the tail sidecar: O(1) append, and the index append hands back
# --------------------------------------------------------------------------------------------

def test_append_indexed_matches_a_full_read_including_across_a_lost_sidecar(tmp_path):
    """The index append returns must equal the one a full re-read finds -- on the fast path, on
    the very first (no-sidecar-yet) append, and on an append made right after the sidecar was
    lost, which is the crash-between-write-and-sidecar-write case."""
    seen = []
    for i in range(4):
        stored, index = ledger.append_indexed({"kind": "test", "k": i}, root=tmp_path)
        seen.append((stored["row_hash"], index))

    (tmp_path / "chain.tail.json").unlink()          # sidecar lost; next append must fall back
    stored, index = ledger.append_indexed({"kind": "test", "k": "after-loss"}, root=tmp_path)
    seen.append((stored["row_hash"], index))

    for i in range(2):                                # and the sidecar rebuilt by that fallback
        stored, index = ledger.append_indexed({"kind": "test", "k": f"post-{i}"}, root=tmp_path)
        seen.append((stored["row_hash"], index))

    assert [index for _h, index in seen] == list(range(7))
    for row_hash, index in seen:
        assert _index_by_reading(tmp_path, row_hash) == index, (row_hash, index)
    assert ledger.verify_chain(root=tmp_path) is None


def test_append_returns_the_row_unchanged_and_still_chains(tmp_path):
    """`append`'s own contract (one dict back, linked to its predecessor) is untouched by the
    index-returning variant it now delegates to."""
    a = ledger.append({"kind": "verdict", "key": "a"}, root=tmp_path)
    b = ledger.append({"kind": "verdict", "key": "b"}, root=tmp_path)
    assert a["prev_hash"] == ""
    assert b["prev_hash"] == a["row_hash"]
    assert [r["key"] for r in _rows_on_disk(tmp_path)] == ["a", "b"]


def test_tail_sidecar_records_the_real_byte_length_not_the_character_count(tmp_path):
    """A row carrying non-ASCII text is longer in bytes than in characters (`ensure_ascii=False`).
    If the sidecar recorded characters, the very next append would see a size mismatch and fall
    back forever -- silently O(n) again, with every test still green."""
    ledger.append({"kind": "test", "k": "日本語 — café"}, root=tmp_path)
    sidecar = json.loads((tmp_path / "chain.tail.json").read_text(encoding="utf-8"))
    assert sidecar["bytes"] == _chain(tmp_path).stat().st_size
    assert sidecar["bytes"] > len(_chain(tmp_path).read_text(encoding="utf-8"))
    assert sidecar["rows"] == 1
    assert sidecar["head_hash"] == _rows_on_disk(tmp_path)[-1]["row_hash"]


def test_append_falls_back_when_the_stream_grew_behind_the_sidecar(tmp_path):
    """An external append leaves the sidecar naming a stale head. The size check catches it and
    the fallback chains from the row actually last on disk, so the chain still verifies."""
    ledger.append({"kind": "test", "k": "a"}, root=tmp_path)
    outsider = ledger.append({"kind": "test", "k": "b"}, root=tmp_path)
    (tmp_path / "chain.tail.json").write_text(                     # rewind the sidecar by a row
        json.dumps({"rows": 1, "head_hash": "0" * 64, "bytes": 10}), encoding="utf-8")

    stored, index = ledger.append_indexed({"kind": "test", "k": "c"}, root=tmp_path)
    assert stored["prev_hash"] == outsider["row_hash"]
    assert index == 2
    assert ledger.verify_chain(root=tmp_path) is None


@pytest.mark.parametrize("bad", [
    "not json at all",
    json.dumps({"rows": -1, "head_hash": "x", "bytes": 0}),
    json.dumps({"rows": "two", "head_hash": "x", "bytes": 0}),
    json.dumps(["rows", 2]),
    json.dumps({"head_hash": "x"}),
])
def test_a_corrupt_tail_sidecar_is_treated_as_an_absent_one(tmp_path, bad):
    """An unusable sidecar must be indistinguishable from no sidecar: read the stream, chain
    correctly, rebuild. It must never raise, and never produce a forked chain."""
    first = ledger.append({"kind": "test", "k": "a"}, root=tmp_path)
    (tmp_path / "chain.tail.json").write_text(bad, encoding="utf-8")
    stored, index = ledger.append_indexed({"kind": "test", "k": "b"}, root=tmp_path)
    assert stored["prev_hash"] == first["row_hash"]
    assert index == 1
    assert ledger.verify_chain(root=tmp_path) is None


def test_append_after_a_corrupt_tail_still_writes_after_the_corrupt_bytes(tmp_path):
    """Today's corrupt-tail semantics, preserved on the fallback path: `read()` stops at the bad
    line, the new row chains from the last WELL-FORMED row, and nothing repairs or rewrites the
    corrupt bytes -- the new row goes after them."""
    good = ledger.append({"kind": "test", "k": "a"}, root=tmp_path)
    with open(_chain(tmp_path), "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    (tmp_path / "chain.tail.json").unlink()          # force the fallback path

    stored, index = ledger.append_indexed({"kind": "test", "k": "b"}, root=tmp_path)
    assert stored["prev_hash"] == good["row_hash"]
    assert index == 1
    raw = _chain(tmp_path).read_text(encoding="utf-8").splitlines()
    assert raw[1] == "{not json", "the corrupt line must survive untouched, in place"
    assert len(raw) == 3
    assert ledger.verify_chain(root=tmp_path) == 1   # still broken at the same row, as before


def test_concurrent_appends_do_not_fork_the_chain_through_the_sidecar(tmp_path, monkeypatch):
    """The sidecar is read and written inside the same exclusive lock as the row, so the
    fast path cannot hand two racing appends the same prev_hash."""
    import threading
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(tmp_path))
    threads = [threading.Thread(target=lambda t=t: [ledger.append({"k": f"{t}-{i}"})
                                                    for i in range(10)])
               for t in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert ledger.verify_chain() is None
    assert len(ledger.read()) == 80
    sidecar = json.loads((tmp_path / "chain.tail.json").read_text(encoding="utf-8"))
    assert sidecar["rows"] == 80
    assert sidecar["bytes"] == _chain(tmp_path).stat().st_size


# --------------------------------------------------------------------------------------------
# B. the verify checkpoint: incremental verification
# --------------------------------------------------------------------------------------------

def test_incremental_verify_agrees_with_the_full_walk_on_a_clean_chain(tmp_path):
    for i in range(6):
        ledger.append({"kind": "test", "k": i}, root=tmp_path)
    assert ledger.verify_chain_incremental(root=tmp_path) is None      # no checkpoint -> full
    checkpoint = json.loads((tmp_path / "chain.verified.json").read_text(encoding="utf-8"))
    assert checkpoint == {"rows": 6, "head_hash": _rows_on_disk(tmp_path)[-1]["row_hash"],
                          "bytes": _chain(tmp_path).stat().st_size}

    for i in range(3):
        ledger.append({"kind": "test", "k": f"more-{i}"}, root=tmp_path)
    assert ledger.verify_chain_incremental(root=tmp_path) is None      # resumed from the checkpoint
    advanced = json.loads((tmp_path / "chain.verified.json").read_text(encoding="utf-8"))
    assert advanced["rows"] == 9
    assert advanced["bytes"] == _chain(tmp_path).stat().st_size
    assert advanced["head_hash"] == _rows_on_disk(tmp_path)[-1]["row_hash"]


def test_incremental_verify_names_the_same_row_as_the_full_walk_for_a_tamper_after_it(tmp_path):
    """A row appended after the checkpoint and then edited must be named by the incremental pass
    at the SAME 0-based index the full walk reports -- indices continue from the checkpoint, they
    do not restart at the resume point."""
    for i in range(5):
        ledger.append({"kind": "test", "k": i}, root=tmp_path)
    assert ledger.verify_chain_incremental(root=tmp_path) is None
    for i in range(3):
        ledger.append({"kind": "test", "k": f"more-{i}"}, root=tmp_path)
    _tamper_field(tmp_path, 6)
    assert ledger.verify_chain(root=tmp_path) == 6
    assert ledger.verify_chain_incremental(root=tmp_path) == 6


def test_incremental_verify_falls_back_to_the_full_walk_on_truncation(tmp_path):
    """A stream shorter than the checkpoint cannot be resumed from it: bytes past the end were
    never verified and are now gone. The full walk runs instead, and reports what it finds."""
    for i in range(5):
        ledger.append({"kind": "test", "k": i}, root=tmp_path)
    assert ledger.verify_chain_incremental(root=tmp_path) is None
    lines = _chain(tmp_path).read_text(encoding="utf-8").splitlines()
    _chain(tmp_path).write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")

    assert ledger.verify_chain_incremental(root=tmp_path) is None       # a clean 3-row prefix
    checkpoint = json.loads((tmp_path / "chain.verified.json").read_text(encoding="utf-8"))
    assert checkpoint["rows"] == 3                                      # re-anchored, not stale


def test_incremental_verify_detects_a_head_row_edited_under_the_checkpoint(tmp_path):
    """The checkpoint's own head row is re-hashed on every incremental pass, so an edit to THAT
    row is caught without a full walk -- the one pre-checkpoint edit the fast path does see."""
    for i in range(5):
        ledger.append({"kind": "test", "k": i}, root=tmp_path)
    assert ledger.verify_chain_incremental(root=tmp_path) is None
    _tamper_field(tmp_path, 4)
    assert ledger.verify_chain_incremental(root=tmp_path) == 4


def test_incremental_verify_misses_a_length_preserving_early_edit_until_the_full_walk(tmp_path):
    """The stated limit of the fast path, asserted rather than only documented: an edit BEFORE
    the checkpoint's head row that keeps the file's byte length the same is invisible to the
    incremental pass, and is caught by the next full walk. This is the cadence's accepted cost."""
    for i in range(5):
        ledger.append({"kind": "test", "k": f"row-{i}"}, root=tmp_path)
    assert ledger.verify_chain_incremental(root=tmp_path) is None
    size_before = _chain(tmp_path).stat().st_size
    _tamper_field(tmp_path, 1, key="k", value="ROW-1")             # same byte length as "row-1"
    assert _chain(tmp_path).stat().st_size == size_before, "the premise of this test"

    assert ledger.verify_chain_incremental(root=tmp_path) is None, "documented blind spot"
    assert ledger.verify_chain_checkpointed(root=tmp_path) == 1, "the full walk still catches it"


def test_an_early_edit_that_changes_the_byte_length_is_caught_incrementally(tmp_path):
    """Not a designed guarantee, but real and worth pinning: an edit before the checkpoint that
    changes how many bytes precede it moves every later byte, so the line ending at the recorded
    offset is no longer the recorded head row. The checkpoint is refused and the full walk runs.
    Only a length-preserving edit slips through."""
    for i in range(5):
        ledger.append({"kind": "test", "k": f"row-{i}"}, root=tmp_path)
    assert ledger.verify_chain_incremental(root=tmp_path) is None
    _tamper_field(tmp_path, 1, key="k", value="a much longer tampered value")
    assert ledger.verify_chain_incremental(root=tmp_path) == 1


def test_incremental_verify_is_vacuously_clean_on_an_absent_or_empty_chain(tmp_path):
    assert ledger.verify_chain_incremental(root=tmp_path) is None       # absent
    assert not (tmp_path / "chain.verified.json").exists()
    _chain(tmp_path).write_text("", encoding="utf-8")
    assert ledger.verify_chain_incremental(root=tmp_path) is None       # empty


def test_a_corrupt_checkpoint_is_treated_as_an_absent_one(tmp_path):
    for i in range(4):
        ledger.append({"kind": "test", "k": i}, root=tmp_path)
    (tmp_path / "chain.verified.json").write_text("{{{", encoding="utf-8")
    assert ledger.verify_chain_incremental(root=tmp_path) is None
    assert json.loads((tmp_path / "chain.verified.json").read_text(encoding="utf-8"))["rows"] == 4


def test_a_checkpoint_naming_a_head_row_that_is_not_there_forces_a_full_walk(tmp_path):
    """A checkpoint whose head row does not re-hash to the recorded value cannot be resumed from
    -- and the full walk it forces must still find a tamper the checkpoint would have skipped."""
    for i in range(5):
        ledger.append({"kind": "test", "k": i}, root=tmp_path)
    size = _chain(tmp_path).stat().st_size
    (tmp_path / "chain.verified.json").write_text(
        json.dumps({"rows": 5, "head_hash": "f" * 64, "bytes": size}), encoding="utf-8")
    _tamper_field(tmp_path, 0)
    assert ledger.verify_chain_incremental(root=tmp_path) == 0


def test_checkpoint_never_claims_more_than_the_walk_verified(tmp_path):
    """The extent is measured before the walk, so a row appended DURING a full walk is left for
    the next pass rather than being checkpointed as verified."""
    for i in range(3):
        ledger.append({"kind": "test", "k": i}, root=tmp_path)
    size_before = _chain(tmp_path).stat().st_size
    real_verify = ledger.verify_chain

    def _verify_then_append(**kwargs):
        result = real_verify(**kwargs)
        ledger.append({"kind": "test", "k": "raced-in"}, root=tmp_path)
        return result

    ledger.verify_chain = _verify_then_append
    try:
        assert ledger.verify_chain_checkpointed(root=tmp_path) is None
    finally:
        ledger.verify_chain = real_verify
    checkpoint = json.loads((tmp_path / "chain.verified.json").read_text(encoding="utf-8"))
    assert checkpoint["rows"] == 3 and checkpoint["bytes"] == size_before


# --------------------------------------------------------------------------------------------
# C. the regression guard: the hot path must not go back to parsing the whole chain
# --------------------------------------------------------------------------------------------

_HOT_STREAM_ROWS = 5000


def _setup_state(tmp_path) -> Path:
    from makoto.record.db import init_db
    state_dir = tmp_path / "makoto_state"
    citations = tmp_path / "CITATIONS.md"
    citations.write_text("Smith 2020\n", encoding="utf-8")
    init_db(state_dir, citations)
    return state_dir


def _dispatch_in_process(monkeypatch, payload: dict) -> int:
    """Run one hook envelope through `_dispatch.main()` IN THIS PROCESS. The existing dispatch
    tests shell out, which is the right call for exit-code and stdout behaviour but useless here:
    a spy installed in the parent is invisible to a subprocess."""
    from makoto import _dispatch
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return _dispatch.main()


class _Spy:
    def __init__(self, fn):
        self._fn = fn
        self.calls = 0

    def __call__(self, *a, **kw):
        self.calls += 1
        return self._fn(*a, **kw)


@pytest.fixture()
def hot_chain(tmp_path, monkeypatch):
    """A state dir whose chain is long enough that an O(n) hot path would be obvious, with both
    sidecars already warmed by one real dispatch."""
    state_dir = _setup_state(tmp_path)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    for i in range(_HOT_STREAM_ROWS):
        ledger.append({"kind": "test", "k": i}, root=state_dir)
    _dispatch_in_process(monkeypatch, {
        "hook_event_name": "PostToolUse", "session_id": "warm", "cwd": str(tmp_path),
        "tool_name": "Bash", "tool_input": {"command": "git status --short"},
        "tool_response": {"stdout": "", "stderr": "", "interrupted": False},
    })
    assert (state_dir / "chain.tail.json").exists()
    assert (state_dir / "chain.verified.json").exists()
    return state_dir


def test_hot_dispatch_never_parses_the_whole_chain(hot_chain, monkeypatch, capsys):
    """THE REGRESSION GUARD. With both sidecars warm, a PreToolUse and a PostToolUse must call
    neither `ledger.read` (a full parse of every row) nor `ledger.verify_chain` (a full re-hash
    of every row) even once. Asserted structurally: wall time on a shared machine is not
    evidence, and a timing threshold generous enough not to flake is too generous to catch a
    regression on a 5000-row chain."""
    read_spy = _Spy(ledger.read)
    verify_spy = _Spy(ledger.verify_chain)
    monkeypatch.setattr(ledger, "read", read_spy)
    monkeypatch.setattr(ledger, "verify_chain", verify_spy)

    assert _dispatch_in_process(monkeypatch, {
        "hook_event_name": "PreToolUse", "session_id": "hot", "cwd": str(hot_chain),
        "tool_input": {"file_path": str(hot_chain / "unrelated.txt"), "content": "hello"},
    }) == 0
    assert _dispatch_in_process(monkeypatch, {
        "hook_event_name": "PostToolUse", "session_id": "hot", "cwd": str(hot_chain),
        "tool_name": "Bash", "tool_input": {"command": "git status --short"},
        "tool_response": {"stdout": "", "stderr": "", "interrupted": False},
    }) == 0
    capsys.readouterr()

    assert read_spy.calls == 0, (
        f"the hot path parsed the whole chain {read_spy.calls} time(s) -- the tail sidecar is "
        "not being used")
    assert verify_spy.calls == 0, (
        f"the hot path re-walked the whole chain {verify_spy.calls} time(s) -- the verify "
        "checkpoint is not being used")


def test_stop_still_walks_the_whole_chain_exactly_once(hot_chain, monkeypatch, capsys):
    """The other half of the cadence: Stop is where the full walk still happens, and it happens
    once. Without this, 'the hot path is fast' could be satisfied by never verifying at all."""
    verify_spy = _Spy(ledger.verify_chain)
    monkeypatch.setattr(ledger, "verify_chain", verify_spy)

    assert _dispatch_in_process(monkeypatch, {
        "hook_event_name": "Stop", "session_id": "hot", "cwd": str(hot_chain),
        "last_assistant_message": "Done.",
    }) == 0
    capsys.readouterr()
    assert verify_spy.calls == 1, f"Stop must run exactly one full walk, ran {verify_spy.calls}"


def test_a_tamper_appended_after_the_warm_checkpoint_is_still_caught_on_a_tool_event(
        hot_chain, monkeypatch, capsys):
    """Speed must not have cost the advisory detection it was protecting: a row appended after
    the warm checkpoint and then edited still trips `dispatch.chain_tamper` on an ordinary
    PreToolUse, and still does not block."""
    ledger.append({"kind": "test", "k": "late"}, root=hot_chain)
    _tamper_field(hot_chain, _HOT_STREAM_ROWS)

    rc = _dispatch_in_process(monkeypatch, {
        "hook_event_name": "PreToolUse", "session_id": "hot", "cwd": str(hot_chain),
        "tool_input": {"file_path": str(hot_chain / "unrelated.txt"), "content": "hello"},
    })
    out = capsys.readouterr().out
    assert rc == 0 and out == "", "chain verification stays advisory -- it must never block"
    facts = [json.loads(ln) for ln
             in (hot_chain / "dispatch_errors.jsonl").read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    assert any(f.get("pattern_id") == "dispatch.chain_tamper" for f in facts), facts
