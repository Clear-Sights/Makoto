"""Plants for the proposed dispatch rows (REGISTER I1-I3). Each FIRE case is red until the rule exists."""
import json
BRIEF = "READ: plugin/makoto/kit.py@3f2a9c1e0b7d\nWRITE: plugin/makoto/kit.py\nACCEPTANCE: python3 -m pytest -q tests/test_kit.py\nFix the off-by-one in unwitnessed."
def pre(tool, prompt): return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"description": "fix", "prompt": prompt}}
def bash(cmd, code=0, out=""): return {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": cmd}, "tool_response": {"stdout": out, "stderr": "", "exitCode": code}}
def stop(t): return {"hook_event_name": "Stop", "last_assistant_message": t}
cases = {
 "i1_catch":  ("event.unbriefed_dispatch", "catch", "FIRE", [pre("Agent", "Fix the off-by-one in kit.unwitnessed and make the tests pass.")], "worker sent with no READ/WRITE/ACCEPTANCE"),
 "i1_reword": ("event.unbriefed_dispatch", "reword", "FIRE", [pre("Task", "Reads: kit.py. Then fix it; tests should pass.")], "same, other tool and loose labels"),
 "i1_pass":   ("event.unbriefed_dispatch", "pass", "ALLOW", [pre("Agent", BRIEF)], "full brief"),
 "i2_catch":  ("event.unpinned_input", "catch", "FIRE", [pre("Agent", BRIEF.replace("@3f2a9c1e0b7d", ""))], "READ path with no content hash"),
 "i2_reword": ("event.unpinned_input", "reword", "FIRE", [{"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "python3 check.py SEED.md", "timeout": 600000}}], "expensive Bash run on an unpinned input"),
 "i2_pass":   ("event.unpinned_input", "pass", "ALLOW", [{"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "sha256sum -c pins.sha256 && python3 check.py SEED.md", "timeout": 600000}}], "input pinned by hash"),
 "i3_catch":  ("gate.unpaid_acceptance", "catch", "FIRE", [pre("Agent", BRIEF), {"user": "status?"}, stop("Done: the off-by-one is fixed.")], "done claimed, ACCEPTANCE never ran"),
 "i3_reword": ("gate.unpaid_acceptance", "reword", "FIRE", [pre("Agent", BRIEF), {"user": "status?"}, bash("python3 -m pytest -q tests/test_kit.py", 1, "1 failed"), stop("The worker finished; kit is fixed.")], "ACCEPTANCE ran and failed"),
 "i3_inflight": ("gate.unpaid_acceptance", "inflight", "ALLOW", [pre("Agent", BRIEF), stop("Dispatched the fix; waiting on the worker.")], "worker dispatched this turn is still in flight"),
 "i3_pass":   ("gate.unpaid_acceptance", "pass", "ALLOW", [pre("Agent", BRIEF), {"user": "status?"}, bash("python3 -m pytest -q tests/test_kit.py", 0, "5 passed"), stop("Done: tests/test_kit.py passes.")], "ACCEPTANCE paid"),
}
OPT_IN = {"makoto.toml": "dispatch = true\n"}  # the working tree opts in; without it every case is silent
rows = ["root\tcase\texpect\tfile\tshows"]
for name, (root, case, exp, evs, shows) in cases.items():
    json.dump({"files": OPT_IN, "events": evs}, open(f"{name}.json", "w"), indent=1)
    rows.append(f"{root}\t{case}\t{exp}\tE/{name}.json\t{shows}")
    if exp == "FIRE":  # the same violation in a tree that did not opt in must stay silent
        json.dump({"events": evs}, open(f"{name}_optout.json", "w"), indent=1)
        rows.append(f"{root}\t{case}_optout\tALLOW\tE/{name}_optout.json\t{shows}, tree not opted in")
open("../proposed.tsv", "w").write("\n".join(rows) + "\n")
