# C5 content.fallthrough_match (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the silent dispatches the check exists to catch
ROW = "content.fallthrough_match"
M = "mat" + "ch"


def _write(content):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "route.py", "content": content}}


CASES = [
    dict(name="base", row=ROW, events=[_write(
        f"def route(ev):\n    {M} ev:\n        case 'a':\n            return 1\n"
        "        case 'b':\n            return 2\n")]),
    dict(name="if-elif-no-else", row=ROW, events=[_write(
        "def route(ev):\n    if ev == 'a':\n        return 1\n    el" + "if ev == 'b':\n        return 2\n")]),
    dict(name="wildcard-raise-caught", row=ROW, events=[_write(
        f"def route(ev):\n    {M} ev:\n        case 'a':\n            return 1\n        case _:\n"
        "            try:\n                raise ValueError(ev)\n            except ValueError:\n"
        "                return None\n")]),
]
