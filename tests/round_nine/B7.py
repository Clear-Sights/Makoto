# B7 content.rule_without_runner (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the unbound rule lines the check exists to catch
ROW = "content.rule_without_runner"
RULE = "Al" + "ways run the linter before a commit."


def _write(path, content):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": path, "content": content}}


CASES = [
    dict(name="base", row=ROW, events=[_write("{cwd}/CLAUDE.md", f"# Rules\n\n{RULE}\n")]),
    dict(name="runner-root", row=ROW,
         events=[_write("{cwd}/CLAUDE.md", f"# Rules\n\n{RULE} run" + "ner: /\n")]),
    dict(name="claude-local", row=ROW, events=[_write("{cwd}/CLAUDE.local.md", f"# Rules\n\n{RULE}\n")]),
]
