"""turn_tool_calls — the events-faithful "did the agent do tool work THIS turn?" primitive.

Production records one PreToolUse event per tool call (install.py wires PreToolUse with matcher '*',
so Bash/Write AND the otherwise-"invisible" Workflow/Agent/Task tools all land in the events table).
A turn's tool calls = the PreToolUse rows after the most recent Stop boundary in the history slice.
This is the discharge signal for the fabricated-action gate: presence of work, immune to command
paraphrase (no text match) and to invisible tools (every tool fires PreToolUse). Token cost is the
temperance-side complement, not this verity signal.
"""
from __future__ import annotations

from makoto.substrate._shared import turn_tool_calls


def _prod(et):
    # production events-table row shape: (id, ts, event_type, cwd, payload)
    return (1, "t", et, "/r", "{}")


def _replay(et):
    # corpus-replay row shape: a dict carrying event_type + payload
    return {"event_type": et, "payload": "{}"}


def test_empty_history_is_zero():
    assert turn_tool_calls([]) == 0
    assert turn_tool_calls(None) == 0


def test_counts_pretooluse_in_current_turn_production_rows():
    h = [_prod("PreToolUse"), _prod("PreToolUse"), _prod("PostToolUse")]
    assert turn_tool_calls(h) == 2          # PostToolUse is the same calls' completion, not a new call


def test_stop_boundary_resets_the_turn():
    # a tool call last turn, then Stop, then a tool-less turn -> THIS turn has 0 tool calls
    h = [_prod("PreToolUse"), _prod("Stop")]
    assert turn_tool_calls(h) == 0
    # a tool call last turn, Stop, then one tool call this turn -> 1
    h2 = [_prod("PreToolUse"), _prod("Stop"), _prod("PreToolUse")]
    assert turn_tool_calls(h2) == 1


def test_counts_replay_dict_rows_too():
    h = [_replay("PreToolUse"), _replay("Stop"), _replay("PreToolUse"), _replay("PreToolUse")]
    assert turn_tool_calls(h) == 2          # since the last Stop


def test_only_last_stop_bounds_the_turn():
    h = [_prod("PreToolUse"), _prod("Stop"), _prod("PreToolUse"), _prod("Stop"), _prod("PreToolUse")]
    assert turn_tool_calls(h) == 1          # only events after the FINAL Stop count
