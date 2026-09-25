"""Focused pin for the Stop/SubagentStop ADVISE spirit gap: `verdict._STOP_WIRE` used to carry
only BLOCK, so an ADVISE-tier Stop gate (18 of them — gate.synthetic_advisory, gate.unasked_plan,
etc.) fired, was recorded to audit.jsonl, and then rendered `{}` on the wire — invisible to the
agent inside the turn. Falsifier: python -m pytest tests/test_stop_advise_reaches_agent.py -q

Fails on old code: `dispatch._emit_decision` always rendered `{}` for a Stop-edge ADVISE finding,
regardless of `stop_hook_active`.
"""
from __future__ import annotations

import io
import json

from makoto import dispatch
from makoto.vocab import Finding


def _advise_finding(pattern_id="gate.synthetic_advisory"):
    return Finding(pattern_id=pattern_id, file="", line=0, level="advisory",
                   message=f"row {pattern_id}: no prior structure read", source_event_id=1)


def _emit(hook_event, stop_hook_active, monkeypatch):
    monkeypatch.setenv("MAKOTO_MODE", "strict")
    stream = io.StringIO()
    dispatch._emit_decision([_advise_finding()], hook_event, stream=stream,
                            stop_hook_active=stop_hook_active)
    return stream.getvalue()


def test_stop_advise_with_stop_hook_active_false_yields_block_carrying_row_id(monkeypatch):
    out = _emit("Stop", False, monkeypatch)
    assert out, "an ADVISE at Stop must reach the agent when stop_hook_active is not true"
    body = json.loads(out)
    assert body["decision"] == "block"
    assert body["hookEventName"] == "Stop"
    assert "gate.synthetic_advisory" in body["reason"]


def test_stop_advise_with_stop_hook_active_true_yields_nothing(monkeypatch):
    out = _emit("Stop", True, monkeypatch)
    assert out == "", "a Stop already bounced once this turn must not be blocked a second time"


def test_stop_advise_defaults_to_not_reactivated(monkeypatch):
    """The caller-omitted default (stop_hook_active=False) is the safe one: an ADVISE still
    reaches the agent when a caller forgets to thread the payload's own flag through."""
    monkeypatch.setenv("MAKOTO_MODE", "strict")
    stream = io.StringIO()
    dispatch._emit_decision([_advise_finding()], "SubagentStop", stream=stream)
    body = json.loads(stream.getvalue())
    assert body["decision"] == "block"
    assert body["hookEventName"] == "SubagentStop"


def test_stop_block_unchanged_regardless_of_stop_hook_active(monkeypatch):
    """A genuine BLOCK at Stop is never suppressed by stop_hook_active — only ADVISE is gated."""
    block = Finding(pattern_id="gate.completion", file="", line=0, level="error",
                    message="row gate.completion: unfinished plan", source_event_id=1)
    for active in (False, True):
        monkeypatch.setenv("MAKOTO_MODE", "strict")
        stream = io.StringIO()
        dispatch._emit_decision([block], "Stop", stream=stream, stop_hook_active=active)
        body = json.loads(stream.getvalue())
        assert body["decision"] == "block"
        assert body["hookEventName"] == "Stop"
