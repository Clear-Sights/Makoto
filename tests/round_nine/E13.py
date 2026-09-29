# E13 gate.relaunched_unchanged (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the unguarded re-launches the check exists to catch
ROW = "gate.relaunched_unchanged"
BRIEF = "Fix the failing import in src/app.py and report back."
CLI = "clau" + "de"


# The ground was read first, so gate.unprobed_fanout is paid and the repeat is what remains.
READ = {"hook_event_name": "PostToolUse", "tool_name": "Read",
        "tool_input": {"file_path": "{cwd}/src/app.py"}, "tool_response": "import x\n"}


def _first_launch():
    return {"hook_event_name": "PostToolUse", "tool_name": "Agent",
            "tool_input": {"description": "fix import", "prompt": BRIEF},
            "tool_response": "The worker could not reach the repository."}


def _pre(tool, tool_input):
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}


CASES = [
    dict(name="base", row=ROW,
         events=[READ, _first_launch(), _pre("Agent", {"description": "fix import", "prompt": BRIEF})]),
    dict(name="mcp-session-message", row=ROW,
         events=[READ, _first_launch(),
                 _pre("mcp__remote__send_message", {"session_id": "session_01abc", "message": BRIEF})]),
    dict(name="bash-claude-p-background", row=ROW,
         events=[READ, _first_launch(),
                 _pre("Bash", {"command": f"nohup {CLI} -p '{BRIEF}' > worker.log 2>&1 &"})]),
]
