# B10 content.check_without_pass_case (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the unpaired checks the check exists to catch
ROW = "content.check_without_pass_case"
C = "Che" + "ck("


def _write(body):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "{cwd}/checks/extra.py", "content": body}}


CASES = [
    dict(name="base", row=ROW, events=[_write("def extra_predicate(ev):\n    return None\n")]),
    dict(name="async-def", row=ROW, events=[_write("async def extra_predicate(ev):\n    return None\n")]),
    dict(name="annotated-row", row=ROW,
         events=[_write(f"EXTRA_CHECK: object = {C}id='x.extra')\n")]),
]
