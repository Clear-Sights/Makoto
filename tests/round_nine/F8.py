# F8 gate.plan_item_drift (docs/attack-round-nine.md, round nine; with its Cross-cutting note).
# makoto-allow: fixtures must spell a forward promise left open at the stop
# Held OUT: the repeat stop with no tool between (withheld by dispatch._unchanged) and the stop
# after three blocks (released by dispatch._spent, STOP_BLOCK_BOUND). Both are the dispatcher's
# stop-churn bound, not this check's reading; the check fires at both stops.
ROW = "gate.plan_item_drift"
PROMISE = {"hook_event_name": "Stop", "last_assistant_message": "Next I'll finish Task #3."}
STOP = {"hook_event_name": "Stop", "last_assistant_message": "Stopping here."}
TOOL = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"},
        "tool_response": {"stdout": "a\n", "stderr": "", "exitCode": 0}}
CASES = [
    dict(name="base", row=ROW, events=[PROMISE, TOOL, STOP]),
]
