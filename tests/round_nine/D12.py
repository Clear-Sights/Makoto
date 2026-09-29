# D12 gate.unknown_ref_switch (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the ref moves the check exists to catch
ROW = "gate.unknown_ref_switch"
SETUP = ("git init -q && git -c user.name=a -c user.email=a@b commit -q --allow-empty -m i "
         "&& git branch feature-x")


def _case(name, cmd):
    return dict(name=name, row=ROW, setup=SETUP,
                events=[{"hook_event_name": "PreToolUse", "tool_name": "Bash",
                         "tool_input": {"command": cmd}}])


CASES = [
    _case("base", "git check" + "out feature-x"),
    _case("reset-keep", "git re" + "set --keep feature-x"),
    _case("rebase", "git re" + "base feature-x"),
]
