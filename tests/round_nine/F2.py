# F2 gate.pasted_fix (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the same repair landing at a second site
ROW = "gate.pasted_fix"
FIX = ("if timeout is None:\n"
       "    timeout = DEFAULT_TIMEOUT\n"
       "if timeout < 0:\n"
       "    raise ValueError(timeout)\n")
OLD = "def load(timeout=None):\n    pass\n"
FILES = {"src/reader.py": OLD, "src/writer.py": OLD}


def _edit(path, new=FIX):
    return {"hook_event_name": "PostToolUse", "tool_name": "Edit",
            "tool_input": {"file_path": "{cwd}/" + path, "old_string": "    pass\n",
                           "new_string": new}, "tool_response": {}}


def _write_existing(path, fix=FIX):
    content = "def load(timeout=None):\n" + "".join("    " + ln + "\n" for ln in fix.splitlines())
    return {"hook_event_name": "PostToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "{cwd}/" + path, "content": content},
            "tool_response": {"type": "update", "filePath": "{cwd}/" + path, "content": content,
                              "originalFile": OLD}}


STOP = {"hook_event_name": "Stop", "last_assistant_message": ""}
PY_REPLACE = ("python3 - <<'PY'\nfrom pathlib import Path\np = Path('src/writer.py')\nnew = '''\n"
              + FIX + "'''\np.write_text(p.read_text().replace('    pass\\n', new))\nPY")
CASES = [
    dict(name="base", row=ROW, files=dict(FILES),
         events=[_edit("src/reader.py"), _edit("src/writer.py"), STOP]),
    dict(name="second-by-write", row=ROW, files=dict(FILES),
         events=[_edit("src/reader.py"), _write_existing("src/writer.py"), STOP]),
    dict(name="second-by-bash-python", row=ROW, files=dict(FILES),
         events=[_edit("src/reader.py"),
                 {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                  "tool_input": {"command": PY_REPLACE},
                  "tool_response": {"stdout": "", "stderr": "", "exitCode": 0}}, STOP]),
]
