"""Makoto rebuilt from the mesh: d(e), S' = D_out(O(V(W(G,C), R(S+e), e), S)), e = D_in(stdin).
Every function here maps to one symbol in MAP.tsv."""
import hashlib, json, os

SETTLED = ("PostToolUse", "PostToolUseFailure")
TURN_MARKS = ("Stop", "SubagentStop", "UserPromptSubmit")   # not Obs; R reads them as turn boundaries

def d_in(raw):                                   # D_in: stdin bytes -> event (fail open)
    try:
        # Python's decoder otherwise accepts non-JSON NaN/Infinity values.
        ev = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, TypeError, RecursionError):
        return None
    if not isinstance(ev, dict):
        return None
    name = ev.get("hook_event_name")
    return ev if isinstance(name, str) and name else None

def sigma_path(state_dir, session_id):           # Sigma: where this session's store lives
    safe = hashlib.sha256(str(session_id).encode()).hexdigest()[:16]
    return os.path.join(state_dir, f"{safe}.jsonl")

def sigma_read(path):                            # Sigma: settled events and fired keys, oldest first
    events, keys = [], set()
    try:
        fh = open(path, encoding="utf-8")
    except FileNotFoundError:
        return events, keys
    with fh:
        for line in fh:
            try:
                row = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            if isinstance(row.get("key"), str):
                keys.add(row["key"])
            elif isinstance(row.get("event"), dict):
                events.append(row["event"])
    return events, keys

def sigma_append(path, row):                     # Sigma: append-only write
    # Validate before creating state: a failed serialization has no store effect.
    line = json.dumps(row, sort_keys=True, allow_nan=False) + "\n"
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)

def o_once(finding, record, keys):               # O: at most once per (row, object, object state)
    if finding is None:
        return None, None
    objs = sorted(set(finding.get("objects") or []))
    wanted = set(objs)
    # Sequence positions are history offsets, not object state. Keep the
    # settled evidence itself so changed results at the same offset can fire.
    state = [
        [o.tool, getattr(o, "input", {}), getattr(o, "output", ""),
         getattr(o, "exit", None), getattr(o, "failed", False),
         sorted(wanted & set(o.objects)), sorted(wanted & set(o.written)),
         sorted(wanted & set(o.created)), getattr(o, "send", ""),
         getattr(o, "search", None)]
        for o in record.obs
        if wanted & (set(o.objects) | set(o.written) | set(o.created))
    ]
    key = hashlib.sha256(json.dumps([finding["row"], objs, state], sort_keys=True).encode()).hexdigest()
    return (None, None) if key in keys else (finding, key)

def d_out(event, finding):                       # D_out: finding? -> hook JSON (two outputs only)
    if event is None or finding is None:
        return {}
    name = event.get("hook_event_name")
    if name not in ("PreToolUse", "Stop", "SubagentStop"):
        return {}
    reason = f"makoto {finding['row']}: {finding['message']}"
    if name == "PreToolUse":
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny", "permissionDecisionReason": reason}}
    return {"decision": "block", "reason": reason}

def main(raw, config, rows, record_fn, evaluate_fn):   # the equation, wired once
    """Evaluate against settled history, then append effects, boundaries and fired keys.

    A current boundary belongs to the next record, so it cannot erase the turn
    being evaluated. Events that cannot emit a decision must not consume keys.
    """
    ev = d_in(raw)
    if ev is None:
        return {}
    name = ev["hook_event_name"]
    path = sigma_path(config["state_dir"], ev.get("session_id", ""))
    events, keys = sigma_read(path)
    record = record_fn(events + ([ev] if name in SETTLED else []))
    finding, key = None, None
    if name in ("PreToolUse", "Stop", "SubagentStop"):
        finding, key = o_once(evaluate_fn(rows, record, ev), record, keys)
    if name in SETTLED + TURN_MARKS:
        sigma_append(path, {"event": ev})
    if key:
        sigma_append(path, {"key": key})
    return d_out(ev, finding)
