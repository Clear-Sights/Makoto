# I1 event.unbriefed_dispatch (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the unbriefed dispatch shapes the check exists to catch
ROW = "event.unbriefed_dispatch"
FILES = {"makoto.toml": "dispatch = true\n"}
# a Read first, so gate.unprobed_fanout (which denies an unprobed dispatch first) is paid
PROBE = {"hook_event_name": "PostToolUse", "tool_name": "Read",
         "tool_input": {"file_path": "{cwd}/makoto.toml"}, "tool_response": "dispatch = true"}
BARE = "Fix the off-by-one in kit." + "unwitnessed and make the tests pass."
EMPTY = "RE" + "AD:\nWRI" + "TE:\nACCEPT" + "ANCE:\n" + BARE


def _agent(prompt):
    return {"hook_event_name": "PreToolUse", "tool_name": "Agent",
            "tool_input": {"description": "fix", "prompt": prompt}}


def _case(name, event):
    return dict(name=name, row=ROW, files=dict(FILES), events=[PROBE, event])


CASES = [
    _case("base", _agent(BARE)),
    _case("empty-labels", _agent(EMPTY)),
    _case("send-message", {"hook_event_name": "PreToolUse",
                           "tool_name": "mcp__claude-code-remote__" + "send_message",
                           "tool_input": {"session_id": "session_01abc", "message": BARE}}),
]
