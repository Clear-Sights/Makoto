# Shared fixture builder for the gate.self_wired entries (B1, B26, D9); underscore: not a case module.
# makoto-allow: fixtures must spell makoto's own hook invocation to wire it
import json

ROW = "gate.self_wired"
INV = "python3 -m " + "mak" + "oto.dispatch"
EVENTS = ("PreToolUse", "PostToolUse", "Stop")
STOP = {"hook_event_name": "Stop", "last_assistant_message": "Done."}


def settings(drop=(), matcher=None, command=None, **extra):
    """A project .claude/settings.json wiring makoto on every event except `drop`; `matcher` and
    `command` override one event's entry: {event: value}."""
    matcher, command = matcher or {}, command or {}
    hooks = {e: [{"matcher": matcher.get(e, "*"),
                  "hooks": [{"type": "command", "command": command.get(e, INV)}]}]
             for e in EVENTS if e not in drop}
    return json.dumps(dict(extra, hooks=hooks))


def case(name, text):
    return dict(name=name, row=ROW, files={".claude/settings." + "json": text}, events=[STOP])
