"""A stop finding the agent was already shown, word for word, with no tool run since, is not sent
again (dispatch._unchanged, register F8 STALE REFIRE). Measured 2026-09-28: 105 of 125 live fires
were such repeats, and on fae0d17 one unclaimed helper blocked four stops in a row.

The finding comes back the moment the agent acts and it still holds, and a claim the new reply
restates is a new instance, so both still block. Every fire stays in the audit, with the withheld
ones listed under `withheld`."""
import json

from tests.conftest import _run_dispatch, _setup_state

_HELPER = "def helper_nobody_asked_for(x):\n    return x + 1\n"


def _write(tmp_path, session):
    return {"hook_event_name": "PostToolUse", "session_id": session, "cwd": str(tmp_path),
            "tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "lib.py"), "content": _HELPER},
            "tool_response": {"filePath": str(tmp_path / "lib.py")}}


def _stop(tmp_path, session, text, active=False):
    return {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
            "last_assistant_message": text, "stop_hook_active": active}


def _blocks(out, check):
    return bool(out) and json.loads(out).get("decision") == "block" and check in json.loads(out)["reason"]


def test_an_unchanged_finding_blocks_once_then_waits_for_an_act(tmp_path):
    # discriminant: a history-derived finding, stops with no tool run between them
    state = _setup_state(tmp_path)
    (tmp_path / "lib.py").write_text(_HELPER)
    _run_dispatch(state, _write(tmp_path, "u"))
    assert _blocks(_run_dispatch(state, _stop(tmp_path, "u", "Added the helper."))[1], "gate.unclaimed_unit")
    assert not _blocks(_run_dispatch(state, _stop(tmp_path, "u", "Added the helper.", active=True))[1],
                       "gate.unclaimed_unit"), "a second stop with nothing done must not loop"
    assert not _blocks(_run_dispatch(state, _stop(tmp_path, "u", "Nothing else."))[1], "gate.unclaimed_unit")
    rows = [json.loads(l) for l in (state / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert [r.get("withheld") for r in rows if "gate.unclaimed_unit" in r["pattern_fires"]][1:] == \
        [["gate.unclaimed_unit"], ["gate.unclaimed_unit"]], "every fire is audited, the repeats as withheld"
    _run_dispatch(state, {"hook_event_name": "PostToolUse", "session_id": "u", "cwd": str(tmp_path),
                          "tool_name": "Bash", "tool_input": {"command": "ls"},
                          "tool_response": {"stdout": "lib.py", "exitCode": 0}})
    assert _blocks(_run_dispatch(state, _stop(tmp_path, "u", "Looked."))[1], "gate.unclaimed_unit"), \
        "after an act, a finding that still holds blocks again"


def test_a_claim_restated_after_its_block_blocks_again(tmp_path):
    # discriminant: a reply-derived finding, the same claim in the next reply
    state = _setup_state(tmp_path)
    assert _blocks(_run_dispatch(state, _stop(tmp_path, "c", "All 602 checks pass."))[1], "gate.unrun_count_claim")
    assert _blocks(_run_dispatch(state, _stop(tmp_path, "c", "All 602 checks pass.", active=True))[1],
                   "gate.unrun_count_claim")
    assert not _blocks(_run_dispatch(state, _stop(tmp_path, "c", "I have not run the checks.", active=True))[1],
                       "gate.unrun_count_claim")


def test_a_check_the_session_never_satisfies_still_lets_the_session_end(tmp_path):
    # discriminant: the same unpayable claim restated at every stop, far past the bound
    from makoto.dispatch import STOP_BLOCK_BOUND
    state = _setup_state(tmp_path)
    outs = [_run_dispatch(state, _stop(tmp_path, "b", "All 602 checks pass.", active=i > 0))[1]
            for i in range(8)]
    blocked = [_blocks(o, "gate.unrun_count_claim") for o in outs]
    assert blocked == [True] * STOP_BLOCK_BOUND + [False] * (8 - STOP_BLOCK_BOUND), \
        "a check blocks a session's stops a bounded number of times"
    assert "gate.unrun_count_claim" in json.loads(outs[-1])["systemMessage"], "the let-through still prints the finding"
