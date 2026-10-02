import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plugin"))
import json, tempfile, collections
from makoto2 import hook
Obs = collections.namedtuple("Obs", "seq tool objects written created")
class Rec:
    def __init__(self, evs): self.obs = [Obs(i, e.get("tool_name"), frozenset(e.get("objs", [])), frozenset(), frozenset()) for i, e in enumerate(evs)]
def ev_(**k): return json.dumps(dict(session_id="s", **k))
def always(rows, rec, ev): return {"row": "r1", "message": "m", "objects": ["x"]} if ev["hook_event_name"] in ("PreToolUse", "Stop") else None
def never(rows, rec, ev): return None
cfg = {"state_dir": tempfile.mkdtemp()}
run = lambda raw, v=always: hook.main(raw, cfg, [], Rec, v)
# D_in fail open
assert run("not json") == {} and run("{}") == {}
# first finding blocks (plant), pre -> deny, stop -> block
a = run(ev_(hook_event_name="PreToolUse", tool_name="Bash"))
assert a["hookSpecificOutput"]["permissionDecision"] == "deny", a
# O: same object state -> silent (look-alike)
assert run(ev_(hook_event_name="PreToolUse", tool_name="Bash")) == {}
# O: object state changes -> blocks again (plant)
run(ev_(hook_event_name="PostToolUse", tool_name="Bash", objs=["x"]), never)
b = run(ev_(hook_event_name="Stop"))
assert b.get("decision") == "block", b
# D_out has two outputs only
assert set(map(lambda d: tuple(sorted(d)), [a, b, {}])) <= {("hookSpecificOutput",), ("decision", "reason"), ()}
print("test_hook OK 6 assertions")
