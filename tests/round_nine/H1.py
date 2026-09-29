# H1 content.unsourced_webfetch (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell unsourced fetches of invented urls the check exists to catch
ROW = "content.unsourced_webfetch"
URL = "https://" + "vendor.example/api/v2/reference"
GH = "https://" + "github.com/acme/widget/blob/main/docs/invented-guide.md"

CASES = [
    dict(name="base", row=ROW, events=[{"hook_event_name": "PreToolUse", "tool_name": "WebFetch",
                                        "tool_input": {"url": URL, "prompt": "summarize"}}]),
    dict(name="bash-curl", row=ROW, events=[{"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                             "tool_input": {"command": "cu" + f"rl -s {URL}"}}]),
    dict(name="invented-github-blob", row=ROW,
         events=[{"hook_event_name": "PreToolUse", "tool_name": "WebFetch",
                  "tool_input": {"url": GH, "prompt": "summarize"}}]),
]
