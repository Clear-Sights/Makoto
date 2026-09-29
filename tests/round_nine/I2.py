# I2 event.unpinned_input (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the unpinned input shapes the check exists to catch
ROW = "event.unpinned_input"
FILES = {"makoto.toml": "dispatch = true\n"}
# a Read first, so gate.unprobed_fanout (which denies an unprobed dispatch first) is paid
PROBE = {"hook_event_name": "PostToolUse", "tool_name": "Read",
         "tool_input": {"file_path": "{cwd}/makoto.toml"}, "tool_response": "dispatch = true"}
H = "3f2a9c1e" + "0b7d"
TAIL = "WRITE: plugin/makoto/kit.py\nACCEPTANCE: python3 -m pytest -q tests/test_kit.py\nFix it."


def _agent(read):
    return {"hook_event_name": "PreToolUse", "tool_name": "Agent",
            "tool_input": {"description": "fix", "prompt": "RE" + "AD: " + read + "\n" + TAIL}}


def _case(name, event):
    return dict(name=name, row=ROW, files=dict(FILES), events=[PROBE, event])


CASES = [
    _case("base", _agent("plugin/makoto/kit.py")),
    _case("comma-joined", _agent("vocab.py,plugin/makoto/kit.py@" + H)),
    _case("unrelated-tag", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                            "tool_input": {"command": "python3 train.py --tag run@" + H,
                                           "timeout": 600000}}),
]
