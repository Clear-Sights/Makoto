# A3 gate.unread_structure (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the null traversals the check exists to catch
ROW = "gate.unread_structure"
STOP = {"hook_event_name": "Stop", "last_assistant_message": "Done."}


def _bash(cmd, out):
    return {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": cmd},
            "tool_response": {"stdout": out, "stderr": "", "exitCode": 0}}


def _read(path, text):
    return {"hook_event_name": "PostToolUse", "tool_name": "Read",
            "tool_input": {"file_path": "{cwd}/" + path}, "tool_response": text}


FILES = {"config.json": '{"a": [1]}\n', "list.json": '[{"id": 1}, {"id": 2}, {"id": 3}]\n',
         "notes.txt": "unrelated\n"}
CASES = [
    dict(name="base", row=ROW, files=dict(FILES),
         events=[_bash("j" + "q '.a.b' config.json", "null"), STOP]),
    dict(name="null-per-element", row=ROW, files=dict(FILES),
         events=[_bash("j" + "q '.[].name' list.json", "null\nnull\nnull"), STOP]),
    dict(name="unrelated-read-first", row=ROW, files=dict(FILES),
         events=[_read("notes.txt", "unrelated\n"), _bash("j" + "q '.a.b' config.json", "null"),
                 STOP]),
]
