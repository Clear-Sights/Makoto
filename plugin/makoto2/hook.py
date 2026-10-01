"""Makoto rebuilt from the mesh: d(e), S' = D_out(O(V(W(G,C), R(S+e), e), S)), e = D_in(stdin).
Every function here maps to one symbol in MAP.tsv."""
import hashlib, json, os, sys, tomllib

SETTLED = ("PostToolUse", "PostToolUseFailure")
TURN_MARKS = ("Stop", "SubagentStop", "UserPromptSubmit")   # not Obs; R reads them as turn boundaries

def d_in(raw):                                   # D_in: stdin bytes -> event (fail open)
    try:
        ev = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return None
    return ev if isinstance(ev, dict) and ev.get("hook_event_name") else None

def sigma_path(state_dir, session_id):           # Sigma: where this session's store lives
    safe = hashlib.sha256(str(session_id).encode()).hexdigest()[:16]
    return os.path.join(state_dir, f"{safe}.jsonl")

def sigma_read(path):                            # Sigma: settled events and fired keys, oldest first
    events, keys = [], set()
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if "key" in row:
                keys.add(row["key"])
            elif "event" in row:
                events.append(row["event"])
    return events, keys

def sigma_append(path, row):                     # Sigma: append-only write
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")

def o_once(finding, record, keys):               # O: at most once per (row, object, object state)
    if finding is None:
        return None, None
    objs = sorted(finding.get("objects") or [])
    state = [(o.seq, o.tool) for o in record.obs if set(objs) & (set(o.objects) | set(o.written) | set(o.created))]
    if "predicate" in finding:
        state = getattr(record, "events", state)
    key = hashlib.sha256(json.dumps([finding["row"], objs, state]).encode()).hexdigest()
    return (None, None) if key in keys else (finding, key)

def d_out(event, finding):                       # D_out: finding? -> hook JSON (two outputs only)
    if finding is None:
        return {}
    reason = f"makoto {finding['row']}: {finding['message']}"
    if event.get("hook_event_name") == "PreToolUse":
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny", "permissionDecisionReason": reason}}
    if event.get("hook_event_name") in ("Stop", "SubagentStop"):
        return {"decision": "block", "reason": reason}
    return {}

def main(raw, config, rows, record_fn, evaluate_fn):   # the equation, wired once
    ev = d_in(raw)
    if ev is None:
        return {}
    # Dispatch is a workspace contract; invalid or absent declarations are off.
    try:
        with open(os.path.join(ev.get("cwd") or os.getcwd(), "makoto.toml"), "rb") as fh:
            declaration = tomllib.load(fh)
            config["dispatch"] = declaration.get("dispatch") is True
            tables = declaration.get("named_sets", {})
            if isinstance(tables, dict):
                config["named_sets"] = {k: v for k, v in tables.items()
                                        if isinstance(v, list) and all(isinstance(x, str) for x in v)}
    except (OSError, ValueError):
        config["dispatch"] = False
        config["named_sets"] = {}
    path = sigma_path(config["state_dir"], ev.get("session_id", ""))
    events, keys = sigma_read(path)
    record = record_fn(events + ([ev] if ev.get("hook_event_name") in SETTLED else []))
    if config["dispatch"]:
        config["dispatch_background"] = {i for i, e in enumerate(events)
                                         if isinstance(e.get("tool_response"), dict)
                                         and e["tool_response"].get("backgroundTaskId")}
        record.dispatch_briefs = [(i, e) for i, e in enumerate(events)
                                  if e.get("hook_event_name") == "PreToolUse"
                                  and e.get("tool_name") in ("Agent", "Task")]
    config["settings"] = {"makoto": {"dispatch": config["dispatch"]}}
    finding, key = o_once(evaluate_fn(rows, record, ev), record, keys)
    if ev.get("hook_event_name") in SETTLED + TURN_MARKS + ("PreToolUse",):
        sigma_append(path, {"event": ev})
    if key:
        sigma_append(path, {"key": key})
    return d_out(ev, finding)
