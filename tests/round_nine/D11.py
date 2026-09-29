# D11 event.thrash_revert (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the revert shapes the check exists to catch
ROW = "event.thrash_revert"
P = "{cwd}/src/app.py"
A = "def f():\n    return 1\n"
B = "def f():\n    return 2\n"


def _post(tool, **ti):
    return {"hook_event_name": "PostToolUse", "tool_name": tool,
            "tool_input": dict(file_path=P, **ti), "tool_response": {}}


def _pre(tool, **ti):
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": dict(file_path=P, **ti)}


CASES = [
    dict(name="base", row=ROW, events=[_post("Write", content=A), _post("Write", content=B),
                                       _pre("Write", content=A)]),
    # A written, B reached by an Edit, A written back
    dict(name="edit-mid", row=ROW,
         events=[_post("Write", content=A), _post("Edit", old_string="return 1", new_string="return 2"),
                 _pre("Write", content=A)]),
    # A, B written, then A restored by an Edit replacing the whole content
    dict(name="whole-edit-revert", row=ROW,
         events=[_post("Write", content=A), _post("Write", content=B),
                 _pre("Edit", old_string=B, new_string=A)]),
]
