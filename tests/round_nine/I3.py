# I3 gate.unpaid_acceptance (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the dispatch briefs and launches the check exists to catch
ROW = "gate.unpaid_acceptance"
ACC = "python3 -m py" + "test -q tests/test_kit.py"
# The operator's turn is stamped after every event the case feeds, so the dispatch is prior-turn.
TURN = ('{"type": "user", "timestamp": "2999-01-01T00:00:00.000000Z", '
        '"message": {"role": "user", "content": "status?"}}\n')
FILES = {"makoto.toml": "dispatch = true\n", "t.jsonl": TURN}
DISPATCH = {"hook_event_name": "PreToolUse", "tool_name": "Agent",
            "tool_input": {"description": "fix",
                           "prompt": ("READ: plugin/makoto/kit.py@3f2a9c1e0b7d\n"
                                      "WRITE: plugin/makoto/kit.py\n"
                                      f"ACCEPTANCE: {ACC}\nFix the off-by-one.")}}
STOP = {"hook_event_name": "Stop", "transcript_path": "{cwd}/t.jsonl",
        "last_assistant_message": "Done: the off-by-one is fixed."}
LAUNCH = {"stdout": "", "stderr": "", "interrupted": False, "isImage": False,
          "noOutputExpected": False, "backgroundTaskId": "b972zfpwn"}


def _post(tool_input, response):
    return {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": tool_input,
            "tool_response": response}


CASES = [
    dict(name="base", row=ROW, files=dict(FILES), events=[DISPATCH, STOP]),
    dict(name="background-launch", row=ROW, files=dict(FILES),
         events=[DISPATCH, _post({"command": ACC, "run_in_background": True}, LAUNCH), STOP]),
    dict(name="timeout-backgrounded", row=ROW, files=dict(FILES),
         events=[DISPATCH, _post({"command": ACC, "timeout": 1000},
                                 dict(LAUNCH, timedOutAfterMs=1000)), STOP]),
]
