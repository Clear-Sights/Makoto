# E11 event.nested_budget (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the shadowed-budget shapes the check exists to catch
ROW = "event.nested_budget"


def _bash(cmd, timeout=None):
    ti = {"command": cmd}
    if timeout is not None:
        ti["timeout"] = timeout
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": ti}


CASES = [
    dict(name="base", row=ROW, events=[_bash("time" + "out 900 make", 600000)]),
    dict(name="python-subprocess-timeout", row=ROW,
         events=[_bash("python3 -c \"import subprocess; subprocess.run(['make'], time" + "out=900)\"",
                       600000)]),
    dict(name="sleep-loop", row=ROW,
         events=[_bash("for i in $(seq 90); do sl" + "eep 10; done", 120000)]),
]
