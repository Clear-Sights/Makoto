"""TIME law: a hook is effectively instantaneous, and stays so as the session grows.

Measured 2026-09-28 through the real shim, one process per hook: Pre 0.11 s, Post 0.08 s, and a
Stop that grew with the session, 0.21 s at 200 recorded events and 0.67 s at 1,200. The growth
was shlex re-parsing every recorded command about thirty times per Stop (36,000 parses for 1,200
events) and the canon atoms recomputed once per fingerprint. After the fix the same Stop reads
0.24 s at 1,200 events.

Two readings hold it, each with its own plant:
- COUNT (deterministic, any machine): one Stop parses each distinct recorded command once.
- TIME (this regime: one process, a synthetic 1,200-event session): every Stop check together
  finishes inside STOP_BOUND_S. The bound is loose against the measured 0.15 s so a slow CI
  runner does not redden it; the COUNT reading is the one that catches a return of the growth.
"""
from __future__ import annotations

import json
import shlex
import time

from makoto.context import GateContext
from makoto.core import _shell
from makoto.registry import load_checks

EVENTS = 1200
STOP_BOUND_S = 2.0


def _history(n=EVENTS):
    rows = []
    for i in range(n):
        ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
              "tool_input": {"command": f"python3 -m pytest -q tests/test_{i}.py && git status"},
              "tool_response": {"stdout": "1 passed", "stderr": "", "exitCode": 0}}
        rows.append({"payload": json.dumps(ev), "event_type": "PostToolUse"})
    return rows


def _ctx(history):
    return GateContext(text="done", touched=frozenset(), empty=frozenset(), testrun_output="",
                       cwd="", fs_exists=lambda p: False, fs_size=lambda p: None,
                       fs_read=lambda p: None, history=history)


def _run_stop(history, extra=()):
    ctx = _ctx(history)
    for check in [*load_checks(edge="Stop"), *extra]:
        try:
            check.run(ctx)
        except Exception:
            pass   # a check's own fault is another law's subject; this one times the edge


def _parses_during_stop(monkeypatch, history):
    calls = []
    real = shlex.shlex

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    getattr(_shell._parsed_segments, "cache_clear", lambda: None)()
    monkeypatch.setattr(shlex, "shlex", counting)
    _run_stop(history)
    return len(calls)


def test_one_stop_parses_each_distinct_command_once(monkeypatch):
    assert _parses_during_stop(monkeypatch, _history()) <= EVENTS


def test_plant_an_uncached_parse_reddens_the_count(monkeypatch):
    # The plant: the parse without its cache, the shape measured before the fix.
    monkeypatch.setattr(_shell, "_parsed_segments", _shell._parsed_segments.__wrapped__)
    assert _parses_during_stop(monkeypatch, _history()) > EVENTS


def test_every_stop_check_together_finishes_inside_the_bound():
    history = _history()
    t = time.perf_counter()
    _run_stop(history)
    assert time.perf_counter() - t < STOP_BOUND_S


def test_plant_a_slow_check_reddens_the_bound():
    # The plant: one more Stop check that takes the whole bound on its own.
    class Slow:
        id, applies_at, posture = "gate.plant_slow", "Stop", "BLOCK"

        @staticmethod
        def run(ctx):
            time.sleep(STOP_BOUND_S)

    t = time.perf_counter()
    _run_stop(_history(10), extra=(Slow,))
    assert time.perf_counter() - t >= STOP_BOUND_S
