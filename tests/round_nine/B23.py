# B23 content.bound_as_count (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the slack-ceiling shapes the check exists to catch


ROW = "content.bound_as_count"
A = "as" + "sert"


def _write(body):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "{cwd}/tests/test_r9.py",
                           "content": f"def test_a():\n    xs = make()\n    {body}\n"}}


CASES = [
    dict(name="base", row=ROW, events=[_write(f"{A} len(xs) <= 5" + "00")]),
    dict(name="reversed", row=ROW, events=[_write(f"{A} 5" + f"00 >= len(xs)")]),
    dict(name="in-range", row=ROW, events=[_write(f"{A} len(xs) in range(5" + "00)")]),
]
