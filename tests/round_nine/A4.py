# A4 content.last_wins (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the repeated-key shapes the check exists to catch


ROW = "content.last_wins"
K = "time" + "out"


def _write(path, text):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": path, "content": text}}


CASES = [
    dict(name="base", row=ROW, events=[_write("{cwd}/cfg.py", f"C = {{'{K}': 30, '{K}': 5}}\n")]),
    dict(name="unpack-override", row=ROW,
         events=[_write("{cwd}/cfg.py", f"C = {{'{K}': 30, **{{'{K}': 5}}}}\n")]),
    dict(name="json-escaped-slash", row=ROW,
         events=[_write("{cwd}/cfg.json", '{"a/b": 1, "a\\' + '/b": 2}\n')]),
]
