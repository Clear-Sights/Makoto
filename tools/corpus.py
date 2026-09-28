"""transcript.jsonl -> turns: [(history_rows, final_text, ts)]; history rows are dicts {payload, event_type}."""
import json, sys, datetime

def ts_of(s):
    try: return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception: return 0.0

def turns(path, window_h=1.5):
    events, pending, out = [], {}, []
    last_text, turn_open = "", False
    for line in open(path, encoding="utf-8"):
        try: r = json.loads(line)
        except Exception: continue
        t = r.get("type"); ts = ts_of(r.get("timestamp", ""))
        msg = r.get("message") or {}
        content = msg.get("content")
        if t == "assistant" and isinstance(content, list):
            for c in content:
                if c.get("type") == "tool_use":
                    pending[c["id"]] = (c.get("name"), c.get("input") or {})
                    if str(c.get("name", "")).endswith("__reply") and (c.get("input") or {}).get("text"):
                        last_text = c["input"]["text"]
                elif c.get("type") == "text" and c.get("text", "").strip():
                    last_text = c["text"]
            turn_open = True
        elif t == "user":
            if isinstance(content, list) and any(c.get("type") == "tool_result" for c in content if isinstance(c, dict)):
                for c in content:
                    if c.get("type") == "tool_result" and c.get("tool_use_id") in pending:
                        name, inp = pending.pop(c["tool_use_id"])
                        body = c.get("content")
                        if isinstance(body, list):
                            body = "\n".join(x.get("text", "") for x in body if isinstance(x, dict))
                        err = bool(c.get("is_error"))
                        resp = {"stdout": body or "", "stderr": "", "exitCode": 1 if err else 0} if name == "Bash" else (body or "")
                        ev = {"hook_event_name": "PostToolUseFailure" if err else "PostToolUse",
                              "tool_name": name, "tool_input": inp, "tool_response": resp}
                        if err: ev["error"] = body or ""
                        events.append((ts, ev))
                        if not str(name).endswith("__reply"): last_text = last_text
            else:
                # a real user turn closes the previous turn
                if turn_open:
                    out.append((_window(events, ts, window_h), last_text, ts))
                turn_open, last_text = False, ""
    return out

def _window(events, now, h):
    return [{"payload": json.dumps(ev), "event_type": ev["hook_event_name"]} for t, ev in events if now - t <= h * 3600]

if __name__ == "__main__":
    ts = turns(sys.argv[1])
    print(len(ts), "turns;", sum(1 for _, x, _ in ts if x), "with a closing reply;", max(len(h) for h, _, _ in ts), "max rows")
