from makoto2.evaluate import repeat_owes, wrote_pays
from makoto2.observed import record


def history(command,exit):
    return record([dict(hook_event_name='PostToolUse',tool_name='Bash',tool_input={'command':command},tool_response={'exitCode':exit})])


def test_repeat_scope_is_append_or_failed_command():
    for command,exit,blocked in [('cat data.tsv',0,False),('printf x >> data.tsv',0,True),('verify',1,True)]:
        ev=dict(hook_event_name='PreToolUse',tool_name='Bash',tool_input={'command':command})
        assert bool(repeat_owes({}, {},history(command,exit),ev)) == blocked
