# A13 gate.claude_identity (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the model identity the check exists to catch
ROW = "gate.claude_identity"
IDENT = "Cl" + "aude <noreply@" + "anthropic.com>"
CFG = "[user]\n\tname = Cl" + "aude\n\temail = noreply@" + "anthropic.com\n"
INIT = "git init -q . && git -c user.name=H -c user.email=h@x.org commit -q --allow-empty -m init"


def _bash(cmd):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd}}


CASES = [
    dict(name="base", row=ROW, setup=INIT + " && git config user.name Cl" + "aude"
         + " && git config user.email noreply@" + "anthropic.com",
         events=[_bash("git commit --allow-empty -m x")]),
    dict(name="include-path", row=ROW, setup=INIT, files={"ident.cfg": CFG},
         events=[_bash("git config include.path ../ident.cfg && git commit --allow-empty -m x")]),
    dict(name="author-from-file", row=ROW, setup=INIT, files={"who.txt": IDENT + "\n"},
         events=[_bash('git -c user.name=H -c user.email=h@x.org commit --allow-empty '
                       '--author "$(cat who.txt)" -m x')]),
]
