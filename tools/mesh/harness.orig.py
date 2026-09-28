"""Drive the INSTALLED makoto end to end: each event is piped through the real hook shim.

usage: python3 harness.py case.json   -> prints one JSON line per event: {i, event, out, err}
case.json: {"transcript": [{"role": "user"|"assistant", "text": ...}, ...]   (optional)
            "files": {"rel/path": "content"}
            an event {"user": text} appends an operator turn to the transcript at that point                                  (optional, written in cwd first)
            "git": true                                                        (optional: git init cwd)
            "events": [hook payload, ...]}   session_id/cwd/transcript_path are filled in.
State dir and HOME are fresh per case, so cases never see each other.
"""
import json, os, re, subprocess, sys, tempfile, pathlib

ROOT = os.environ.get("MAKOTO_ROOT") or "/root/.claude/plugins/synced/d8591e5a-3e95-4e79-9738-476705c666e2_801069ae-5e0a-471b-87b4-a8ee931b93c5/makoto"


def load(path):
    """A case may name the plugin under test as {ROOT}."""
    return json.loads(open(path).read().replace("{ROOT}", ROOT))


def run(case):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mkprobe-"))
    cwd = tmp / "work"; cwd.mkdir()
    home = tmp / "home"; (home / ".claude").mkdir(parents=True)
    if case.get("git"):
        subprocess.run(["git", "init", "-q", str(cwd)], check=True)
    for rel, body in case.get("files", {}).items():
        p = cwd / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(body)
    tpath = tmp / "transcript.jsonl"
    with tpath.open("w") as f:
        for k, t in enumerate(case.get("transcript", [])):
            ts = t.get("ts", f"2026-01-01T00:00:{k:02d}.000Z")
            if t["role"] == "user":
                f.write(json.dumps({"type": "user", "timestamp": ts, "message": {"role": "user", "content": t["text"]}}) + "\n")
            else:
                f.write(json.dumps({"type": "assistant", "timestamp": ts, "message": {"role": "assistant",
                        "content": [{"type": "text", "text": t["text"]}]}}) + "\n")
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=ROOT, HOME=str(home),
               MAKOTO_STATE_DIR=str(home / ".claude" / "makoto_state"))
    env.pop("MAKOTO_DISABLE_PATTERNS", None)
    outs = []
    for i, ev in enumerate(case["events"]):
        if "user" in ev:  # an operator turn at this point of the session, stamped now
            import datetime
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            with tpath.open("a") as f:
                f.write(json.dumps({"type": "user", "timestamp": ts, "message": {"role": "user", "content": ev["user"]}}) + "\n")
            continue
        ev = dict(ev)
        ev.setdefault("session_id", "probe-session")
        ev.setdefault("cwd", str(cwd))
        ev.setdefault("transcript_path", str(tpath))
        if ev.get("hook_event_name") in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
            ev.setdefault("tool_use_id", f"toolu_{i:04d}")
        r = subprocess.run(["sh", f"{ROOT}/makoto/_dispatch_shim.sh"], input=json.dumps(ev),
                           capture_output=True, text=True, cwd=str(cwd), env=env, timeout=120)
        outs.append({"i": i, "event": ev.get("hook_event_name"), "tool": ev.get("tool_name"),
                     "out": r.stdout.strip(), "err": r.stderr.strip()[-600:], "rc": r.returncode})
    return outs


def verdict(outs):
    """BLOCK if any event denied/blocked; the ids named; else ALLOW."""
    ids, blocked = set(), False
    for o in outs:
        s = o["out"]
        if '"deny"' in s or '"block"' in s:
            blocked = True
        ids |= set(re.findall(r"\b(?:gate|content|event)\.[a-z_A-Z]+", s + " " + o["err"]))
    return blocked, sorted(ids)


if __name__ == "__main__":
    outs = run(load(sys.argv[1]))
    for o in outs:
        print(json.dumps(o))
    b, ids = verdict(outs)
    print(json.dumps({"blocked": b, "ids": ids}))
