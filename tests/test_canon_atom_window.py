"""The ATOM WINDOW: canon atoms are evaluated over the calls since the operator last spoke.

Every atom is `_existing(calls, pred)`, an existential. Given the whole session those are
MONOTONE -- once a green run and a timeout have each happened, both are permanently true, so
`nosrc_green_timeout` can never stop matching however the agent behaves afterwards. The typed
`release.operator` phrase is then its only exit, which is what forces a human onto a gate whose
whole premise is that a claim is held against the record and not against an utterance.

Reported by AliceLJY as the "secondary, lower priority" half of issue #45; it is the primary
defect of the two. Tracked as #57.

Four directions, each a way the fix could be wrong rather than four ways it could be right:
  fires again on repetition          -- the gate is windowed, not disabled
  silent when the agent has stopped  -- monotonicity is actually gone
  a tool result does not reset       -- the boundary is a GENUINE operator turn
  no transcript means no window      -- an unestablished window never widens what passes
"""
from __future__ import annotations

import json

from makoto.checks.canonFingerprints import canon_fingerprint_block_gate
from makoto.substrate._canonAtoms import calls_since

T0, T1, T2 = "2026-09-08T10:00:00Z", "2026-09-08T11:00:00Z", "2026-09-08T12:00:00Z"


def _ev(tool_name, tool_input, tool_response):
    return {"hook_event_name": "PostToolUse", "tool_name": tool_name,
            "tool_input": tool_input, "tool_response": tool_response}


def _row(ts, tool_name, tool_input, **result):
    """A history row in `_select_recent` shape: (id, ts, event_type, cwd, payload)."""
    return (1, ts, "PostToolUse", "/w", json.dumps(_ev(tool_name, tool_input, result)))


def _green(ts):
    return _row(ts, "Bash", {"command": "pytest -q"}, stdout="3 passed in 0.1s", stderr="")


def _timeout(ts):
    return _row(ts, "Bash", {"command": "slow-thing"}, interrupted=True)


def _transcript(tmp_path, entries):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return str(p)


def _operator(text, ts):
    return {"type": "user", "message": {"role": "user", "content": text}, "timestamp": ts}


def _fires(history, transcript_path):
    return {f.message.split(":")[0].replace("canon.", "")
            for f in canon_fingerprint_block_gate("", history, transcript_path=transcript_path)}


# ---- the window itself ------------------------------------------------------------------------
def test_calls_before_the_operator_turn_are_outside_the_window():
    history = [_green(T0), _timeout(T0), _green(T2)]
    assert len(calls_since(history, None)) == 3, "no window means the whole session"
    assert len(calls_since(history, T1)) == 1, "only the call after the boundary survives"


def test_a_row_whose_ts_cannot_be_read_is_kept():
    """Narrowing the window on a decode failure would let a decode failure quiet a gate."""
    assert len(calls_since([{"payload": json.dumps(
        _ev("Bash", {"command": "pytest -q"}, {"stdout": "3 passed"}))}], T1)) == 1


# ---- the four directions ----------------------------------------------------------------------
def test_monotonicity_is_gone_once_the_operator_has_spoken(tmp_path):
    """The same call stream that fires must stop firing when a genuine turn separates it."""
    history = [_green(T0), _timeout(T0)]
    before = _transcript(tmp_path, [_operator("go on", T0)])
    assert "nosrc_green_timeout" in _fires(history, before), "must fire with no window"
    after = _transcript(tmp_path, [_operator("I looked, it is fine", T1)])
    assert _fires(history, after) == set(), "the operator spoke after it; nothing has repeated"


def test_it_fires_again_when_the_agent_repeats_the_pattern(tmp_path):
    """Windowed is not disabled: the same conduct after being told still blocks."""
    history = [_green(T0), _timeout(T0), _green(T2), _timeout(T2)]
    t = _transcript(tmp_path, [_operator("noted, carry on", T1)])
    assert "nosrc_green_timeout" in _fires(history, t)


def test_a_tool_result_turn_does_not_reset_the_window(tmp_path):
    """The agent must not be able to manufacture a reset. `_is_genuine_user_turn` is the boundary
    and it refuses a turn carrying toolUseResult, so this transcript has NO genuine turn -- which
    means no window, which means the fingerprint still fires."""
    history = [_green(T0), _timeout(T0)]
    fake = {"type": "user", "message": {"role": "user", "content": "done"},
            "toolUseResult": {"stdout": "ok"}, "timestamp": T1}
    assert "nosrc_green_timeout" in _fires(history, _transcript(tmp_path, [fake]))


def test_a_synthetic_turn_does_not_reset_the_window(tmp_path):
    history = [_green(T0), _timeout(T0)]
    synth = _operator("<system-reminder>keep going</system-reminder>", T1)
    assert "nosrc_green_timeout" in _fires(history, _transcript(tmp_path, [synth]))


def test_no_transcript_means_no_window(tmp_path):
    """An unestablished window is the whole session -- the strict direction, and the behaviour
    before the window existed. It must never widen what the gate lets through."""
    history = [_green(T0), _timeout(T0)]
    assert "nosrc_green_timeout" in _fires(history, None)
    assert "nosrc_green_timeout" in _fires(history, str(tmp_path / "absent.jsonl"))
