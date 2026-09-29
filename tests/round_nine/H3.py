# H3 gate.pasted_fix (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the same repair landing at a second site
ROW = "gate.pasted_fix"
FIX = ("if value is None:\n"
       "    value = DEFAULT_LIMIT\n"
       "if value < 0:\n"
       "    raise ValueError(value)\n")
OLD = "def load(timeout=None):\n    pass\n"
FILES = {"src/reader.py": OLD, "src/writer.py": OLD}


def _edit(path, new):
    return {"hook_event_name": "PostToolUse", "tool_name": "Edit",
            "tool_input": {"file_path": "{cwd}/" + path, "old_string": "    pass\n",
                           "new_string": new}, "tool_response": {}}


def _write_existing(path, fix):
    content = "def load(timeout=None):\n" + "".join("    " + ln + "\n" for ln in fix.splitlines())
    return {"hook_event_name": "PostToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "{cwd}/" + path, "content": content},
            "tool_response": {"type": "update", "filePath": "{cwd}/" + path, "content": content,
                              "originalFile": OLD}}


STOP = {"hook_event_name": "Stop", "last_assistant_message": ""}
CASES = [
    dict(name="base", row=ROW, files=dict(FILES),
         events=[_edit("src/reader.py", FIX), _edit("src/writer.py", FIX), STOP]),
    dict(name="identifier-renamed", row=ROW, files=dict(FILES),
         events=[_edit("src/reader.py", FIX),
                 _edit("src/writer.py", FIX.replace("value", "amount")), STOP]),
    dict(name="existing-file-by-write", row=ROW, files=dict(FILES),
         events=[_edit("src/reader.py", FIX), _write_existing("src/writer.py", FIX), STOP]),
]
