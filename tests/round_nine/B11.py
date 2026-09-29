# B11 gate.unprobed_fanout (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the unprobed dispatches the check exists to catch
ROW = "gate.unprobed_fanout"
BRIEF = "Refactor the parser in src/parse.py to stream its input."
CLI = "clau" + "de"


def _pre(tool, tool_input):
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}


CASES = [
    dict(name="base", row=ROW, events=[_pre("Agent", {"description": "refactor", "prompt": BRIEF})]),
    dict(name="mcp-message", row=ROW,
         events=[_pre("mcp__remote__send_message", {"session_id": "session_01abc", "message": BRIEF})]),
    dict(name="bash-claude-p", row=ROW, events=[_pre("Bash", {"command": f"{CLI} -p '{BRIEF}'"})]),
]
