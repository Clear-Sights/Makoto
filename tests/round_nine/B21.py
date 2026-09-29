# B21 content.overdetermined_case (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the undiscriminated verdict cases the check exists to catch
ROW = "content.overdetermined_case"
D = "d" + "ef "


def _write(content):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "test_rows.py", "content": content}}


def _two(a, b, prefix=""):
    return _write(f"{prefix}{D}{a}():\n    assert f(1)\n\n\n{prefix}{D}{b}():\n    assert f(2)\n")


CASES = [
    dict(name="base", row=ROW, events=[_two("test_a_" + "fires", "test_b_" + "fires")]),
    dict(name="verdict-synonym", row=ROW, events=[_two("test_rejects_one", "test_rejects_two")]),
    dict(name="async-def", row=ROW,
         events=[_two("test_" + "fires_one", "test_" + "fires_two", prefix="async ")]),
]
