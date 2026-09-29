# E10 event.identical_retry (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the deterministic-failure retries the check exists to catch
ROW = "event.identical_retry"
CMD = "python3 tool.py"


def _case(name, stderr):
    pre = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": CMD}}
    post = dict(pre, hook_event_name="PostToolUse",
                tool_response={"stdout": "", "stderr": stderr, "exitCode": 1})
    return dict(name=name, row=ROW, events=[pre, post, pre])


TB = "Traceback (most recent call last):\n  File \"tool.py\", line {n}, in <module>\n    {src}\n"
CASES = [
    _case("base", "  File \"tool.py\", line 12\n    def f(\n         ^\nSyntax" + "Error: '(' was never closed\n"),
    _case("syntax-line-503", "  File \"tool.py\", line 503\n    def f(\n         ^\nSyntax" + "Error: '(' was never closed\n"),
    _case("keyerror", TB.format(n=7, src="cfg['name']") + "Key" + "Error: 'name'\n"),
]
