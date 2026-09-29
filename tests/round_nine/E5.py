# E5 event.identical_retry (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the deterministic-failure retries the check exists to catch
ROW = "event.identical_retry"
CMD = "python3 -c 'import no_such_" + "module'"
FAIL = {"stdout": "", "exitCode": 1,
        "stderr": "Traceback (most recent call last):\n  File \"<string>\", line 1, in <module>\n"
                  "ModuleNot" + "FoundError: No module named 'no_such_module'\n"}


def _pre(cmd, desc=None):
    ti = {"command": cmd}
    if desc:
        ti["description"] = desc
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": ti}


def _post(cmd, desc=None):
    return dict(_pre(cmd, desc), hook_event_name="PostToolUse", tool_response=dict(FAIL))


CASES = [
    dict(name="base", row=ROW, events=[_pre(CMD), _post(CMD), _pre(CMD)]),
    dict(name="description-differs", row=ROW,
         events=[_pre(CMD, "Import it"), _post(CMD, "Import it"), _pre(CMD, "Try the import again")]),
    dict(name="read-between", row=ROW, files={"notes.txt": "x\n"},
         events=[_pre(CMD), _post(CMD),
                 {"hook_event_name": "PreToolUse", "tool_name": "Read",
                  "tool_input": {"file_path": "{cwd}/notes.txt"}},
                 {"hook_event_name": "PostToolUse", "tool_name": "Read",
                  "tool_input": {"file_path": "{cwd}/notes.txt"},
                  "tool_response": {"type": "text", "file": {"filePath": "{cwd}/notes.txt",
                                                             "content": "x\n"}}},
                 _pre(CMD)]),
]
