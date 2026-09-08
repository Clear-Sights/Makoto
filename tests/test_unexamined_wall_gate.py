"""gate.unexamined_wall -- register entry G5's runner.

Every cell here drives the shipped gate function. The two that matter most are the negative
ones: a wall stated AFTER acting must be silent, and a non-epistemic refusal must be silent,
because those are the two ways this gate could become a paraphrase judge.
"""
import json

from makoto.checks.unexaminedWall import unexamined_wall_gate

_T0 = "2026-09-08T20:00:00.000Z"
_T1 = "2026-09-08T21:00:00.000Z"


def _transcript(tmp_path, *turns):
    """A JSONL transcript of genuine, host-written operator turns."""
    p = tmp_path / "transcript.jsonl"
    p.write_text("".join(
        json.dumps({"timestamp": ts, "message": {"role": "user", "content": text}}) + "\n"
        for text, ts in turns), encoding="utf-8")
    return str(p)


def _call(name, ts):
    """A history row in the dispatcher's own shape: (id, ts, event_type, cwd, payload)."""
    return (1, ts, "PostToolUse", "/tmp", json.dumps(
        {"hook_event_name": "PostToolUse", "tool_name": name,
         "tool_input": {}, "tool_response": {}}))


def test_epistemic_wall_with_no_acts_since_the_operator_spoke_blocks(tmp_path):
    tp = _transcript(tmp_path, ("go on then", _T0))
    f = unexamined_wall_gate("There is no way to tell whether the suite passes.",
                             history=[], transcript_path=tp)
    assert f is not None
    assert f.pattern_id == "gate.unexamined_wall"
    assert f.level == "error"


def test_the_same_wall_after_one_act_is_silent(tmp_path):
    """THE control. Without this cell the gate is 'says cannot' and not 'says cannot unlooked'."""
    tp = _transcript(tmp_path, ("go on then", _T0))
    f = unexamined_wall_gate("There is no way to tell whether the suite passes.",
                             history=[_call("Bash", _T1)], transcript_path=tp)
    assert f is None


def test_an_act_before_the_operator_turn_does_not_count(tmp_path):
    """The window is per-turn. An act from BEFORE the operator spoke is not looking THIS time --
    which is the whole reason the atom window exists rather than a whole-session existential."""
    tp = _transcript(tmp_path, ("go on then", _T1))
    f = unexamined_wall_gate("I cannot determine whether the branch is pushed.",
                             history=[_call("Bash", _T0)], transcript_path=tp)
    assert f is not None


def test_a_refusal_is_not_a_wall(tmp_path):
    """Excluded by design: refusing a request asserts nothing about what is knowable."""
    tp = _transcript(tmp_path, ("do the thing", _T0))
    for text in ("I can't help with that.",
                 "I won't do that.",
                 "Models cannot browse the web."):
        assert unexamined_wall_gate(text, history=[], transcript_path=tp) is None, text


def test_no_operator_turn_is_silent_not_blocking(tmp_path):
    """A window that cannot be established must never widen what is blocked."""
    tp = _transcript(tmp_path)
    assert unexamined_wall_gate("There is no way to tell whether the suite passes.",
                                history=[], transcript_path=tp) is None


def test_absent_transcript_is_silent(tmp_path):
    assert unexamined_wall_gate("There is no way to tell if it passed.",
                                history=[], transcript_path=str(tmp_path / "nope.jsonl")) is None
    assert unexamined_wall_gate("There is no way to tell if it passed.",
                                history=[], transcript_path=None) is None


def test_clean_text_never_fires(tmp_path):
    tp = _transcript(tmp_path, ("go on", _T0))
    assert unexamined_wall_gate("The suite passes: 1979 passed, 1 xfailed.",
                                history=[], transcript_path=tp) is None


def test_the_check_can_fail(tmp_path):
    """The plant: neutralise the window test and the control cell must go red."""
    tp = _transcript(tmp_path, ("go on then", _T0))
    blocked = unexamined_wall_gate("There is no way to tell whether the suite passes.",
                                   history=[], transcript_path=tp)
    silent = unexamined_wall_gate("There is no way to tell whether the suite passes.",
                                  history=[_call("Bash", _T1)], transcript_path=tp)
    assert blocked is not None and silent is None, (
        "the gate must distinguish the two by the act stream alone; if both come back the same, "
        "it has become a text matcher")
