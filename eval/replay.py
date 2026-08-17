#!/usr/bin/env python3
"""Replay recorded sessions through the hook and show where it fires.

Each corpus file is one session: a JSON header line, then hook events in order.
The header names the event where the real pattern derailed (`derails_at`, 0-based
index into the events). The claim under test is narrow and mechanical:

    the hook fires at or before the derailing event, and its decision at that
    moment would have denied the call (or blocked the stop) with a stated reason.

This is not a behaviour experiment. It proves the trigger, not the outcome: a
live agent receiving the denial may still find another path. What it makes
reproducible is that the moment the corpus went wrong is a moment this hook
speaks, and what it would have said.

Sessions with `"expect": "none"` are controls: the hook must stay silent for
every event. Sessions with `"expect": "recovery"` additionally require that the
same call, made again after the guard, passes — denial is a repricing, not a
prohibition.

Run from the repository root:

    python3 eval/replay.py

Exit 0 iff every session meets its expectation. Python standard library only.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS = pathlib.Path(__file__).resolve().parent / "corpus"

DISPATCH_CWD = ROOT
STATE_ENV = "MAKOTO_STATE_DIR"


def dispatch(event: dict, state_dir: str) -> dict:
    env = dict(os.environ, **{STATE_ENV: state_dir})
    proc = subprocess.run(
        [sys.executable, "-m", "makoto.dispatch"],
        input=json.dumps(event), capture_output=True, text=True,
        cwd=DISPATCH_CWD, env=env,
    )
    try:
        decision = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        decision = {}
    return {"decision": decision, "exit": proc.returncode}


def fired(result: dict) -> str | None:
    """Return the denial/block reason if this decision stops the call, else None."""
    decision = result["decision"]
    hook = decision.get("hookSpecificOutput", {})
    if hook.get("permissionDecision") == "deny":
        return hook.get("permissionDecisionReason", "(denied, no reason field)")
    if decision.get("decision") == "block":
        return decision.get("reason", "(blocked, no reason field)")
    if result["exit"] == 2:
        return "(exit 2: block)"
    return None


def replay(path: pathlib.Path) -> bool:
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    header, events = lines[0], lines[1:]
    expect = header.get("expect", "fires")
    with tempfile.TemporaryDirectory() as state:
        results = [dispatch(event, state) for event in events]

    reasons = [fired(result) for result in results]
    first = next((i for i, reason in enumerate(reasons) if reason), None)

    print(f"\n== {path.stem}: {header['description']}")
    if expect == "none":
        ok = first is None
        print("   control session: " + ("silent on every event — OK"
              if ok else f"UNEXPECTED fire at event {first}: {reasons[first]}"))
        return ok

    derails_at = header["derails_at"]
    print(f"   derailing event [{derails_at}]: {header['derailment']}")
    if first is None:
        print("   FAIL: the hook never fired")
        return False
    print(f"   first fire at event [{first}]: {reasons[first]}")
    ok = first <= derails_at
    print("   fires at or before the derailment — OK" if ok
          else "   FAIL: first fire comes after the derailing event")

    if expect == "recovery":
        last = len(events) - 1
        recovered = reasons[last] is None
        print("   same call after the guard passes — OK" if recovered
              else f"   FAIL: still denied after the guard: {reasons[last]}")
        ok = ok and recovered
    return ok


def main() -> int:
    paths = sorted(CORPUS.glob("*.jsonl"))
    if not paths:
        print(f"no corpus sessions found in {CORPUS}", file=sys.stderr)
        return 1
    outcomes = [replay(path) for path in paths]
    passed = sum(outcomes)
    print(f"\nREPLAY sessions={len(outcomes)} passed={passed} failed={len(outcomes) - passed}")
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
