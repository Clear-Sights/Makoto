# B34 content.exemption_unnamed_region (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the unnamed exemption lists the check exists to catch
ROW = "content.exemption_unnamed_region"


def _write(content):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "lint_check.py", "content": content}}


CASES = [
    dict(name="base", row=ROW, events=[_write("_S" + "KIP_PATHS = ['vendor/']\n")]),
    dict(name="frozenset-wrapped", row=ROW, events=[_write("S" + "KIP_PATHS = frozenset({'vendor/'})\n")]),
    dict(name="whitelist-name", row=ROW, events=[_write("WHITE" + "LIST = ['vendor/']\n")]),
]
