# E3 content.illusory_authorship_trailer (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the attribution shapes the check exists to catch
ROW = "content.illusory_authorship_trailer"
M = "Cl" + "aude"
A = "noreply@" + "anthropic.com"


def _bash(cmd):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd}}


CASES = [
    dict(name="base", row=ROW, events=[_bash(f'git commit -m "x\n\nCo-Authored-By: {M} <{A}>"')]),
    dict(name="trailer-equals", row=ROW,
         events=[_bash(f'git commit -m x --trailer "Co-authored-by={M} <{A}>"')]),
    dict(name="assisted-by", row=ROW, events=[_bash(f'git commit -m "x\n\nAssisted-by: {M} Opus"')]),
    dict(name="verb-using", row=ROW, events=[_bash(f'git commit -m "x\n\nGenerated using {M} Code"')]),
    dict(name="author-model", row=ROW, events=[_bash(f'git commit --author="{M} <{A}>" -m x')]),
    dict(name="printf-hex", row=ROW,
         events=[_bash('git commit -m "x" -m "$(printf \'Co-Authored-By: \\x43laude <x@y>\')"')]),
    dict(name="pr-body-cowrote", row=ROW,
         events=[{"hook_event_name": "PreToolUse", "tool_name": "Write",
                  "tool_input": {"file_path": "PR_BODY.md",
                                 "content": f"## Summary\n\nFix x.\n\n{M} co-wrote this change.\n"}}]),
]
