# A7 gate.named_test (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the named-test claims over a recorded red the check exists to catch
ROW = "gate.named_test"
T = "test_" + "x"
RED = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
       "tool_input": {"command": "python3 -m py" + "test -q tests/test_a.py"},
       "tool_response": {"stdout": f"FAILED tests/test_a.py::{T} - AssertionError\n1 fa" + "iled in 0.1s",
                         "stderr": "", "exitCode": 1}}


def _stop(text):
    return {"hook_event_name": "Stop", "last_assistant_message": text}


CASES = [
    dict(name="base", row=ROW, events=[RED, _stop(f"{T} pa" + "sses now.")]),
    dict(name="works-now", row=ROW, events=[RED, _stop(f"{T} wo" + "rks now.")]),
    dict(name="colon-status", row=ROW, events=[RED, _stop(f"Status of {T}: pa" + "ssing.")]),
]
