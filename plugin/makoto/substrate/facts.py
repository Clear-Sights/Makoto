"""Hook events as the facts substrate/line.py reads (START step 13): one dict per event with
event, tool, path, args, exit, output, cwd, claim{kind, subject}, and source{read{path: hash}},
the read ledger. No model; every field is a token or regex reading of one recorded event.

The ledger's hashes come from `stamp`, which the dispatcher applies to a settled Read, Write or
Edit before the event is stored: the file's hash as this session saw it. Replayed history then
carries what was seen, so drift (a file cited after it changed since it was last seen) is a line.
"""
from __future__ import annotations

import hashlib
import os
import re

import shlex

from makoto.kit import claim as _claim, command_of, is_test_runner, response_text
from makoto.vocab import _lazy_re

SEEN_KEY = "makoto_seen_hash"
_EVENT = {"PreToolUse": "Pre", "PostToolUse": "Post", "PostToolUseFailure": "Post", "Stop": "Stop",
          "SubagentStop": "Stop", "SessionStart": "Start", "PreCompact": "PreCompact",
          "UserPromptSubmit": "Prompt"}
_SEEING_TOOLS = ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit")
_MAX_HASHED = 8 * 1024 * 1024

# The claim reader: a word table (kind -> the words that make a sentence that kind of claim), each
# read through kit.claim, so a quoted, negated or forward-framed sentence is not a claim.
CLAIM_WORDS = {
    "clean": _lazy_re(r"\b(?:passes|passed|pass|green|clean|succeeds?|succeeded)\b", re.I),
    "plan": _lazy_re(r"\b(?:here(?:'s| is) (?:the|my) plan|my plan is|the plan is|i(?:'ll| will) "
                     r"(?:start|begin) by)\b", re.I),
    "question": _lazy_re(r"\?\s*$", re.M),
    "helps": _lazy_re(r"\b(?:helps|improves|reduces|speeds up|\d+(?:\.\d+)?\s*%\s*(?:faster|fewer|"
                      r"cheaper|smaller))\b", re.I),
}
_SUBJECT_RX = _lazy_re(r"`([^`\n]+)`")


def _path_of(ev: dict) -> str | None:
    ti = ev.get("tool_input") if isinstance(ev.get("tool_input"), dict) else {}
    p = ti.get("file_path") or ti.get("notebook_path") or ti.get("path")
    return p if isinstance(p, str) and p else None


def file_hash(path: str):
    try:
        if os.path.getsize(path) > _MAX_HASHED:
            return None
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except OSError:
        return None


def _seen_paths(payload: dict) -> list:
    """The files a settled call showed the session: a Read/Write/Edit's path, or every argument of a
    Bash command that names an existing file (`cat`, `sed -n`, `grep ... file`)."""
    if payload.get("tool_name") in _SEEING_TOOLS:
        p = _path_of(payload)
        return [p] if p else []
    if payload.get("tool_name") == "Bash":
        try:
            words = shlex.split(command_of(payload) or "")
        except ValueError:
            return []
        cwd = payload.get("cwd") or "."
        return [w for w in words[:64] if "/" in w or "." in w
                if not w.startswith("-") and os.path.isfile(w if os.path.isabs(w) else os.path.join(cwd, w))]
    return []


def stamp(payload: dict) -> dict | None:
    """The payload with {path: hash} of each file it showed the session, for a settled call; else None."""
    if payload.get("hook_event_name") != "PostToolUse":
        return None
    cwd = payload.get("cwd") or "."
    seen = {}
    for p in _seen_paths(payload):
        h = file_hash(p if os.path.isabs(p) else os.path.join(cwd, p))
        if h is not None:
            seen[p] = h
    return {**payload, SEEN_KEY: seen} if seen else None


def read_claim(text: str) -> dict:
    """{kind, subject} of the first claim sentence in `text`, by the word table; {} for none."""
    for kind, rx in CLAIM_WORDS.items():
        m = _claim(text or "", rx)
        if m is not None:
            start = (text or "").rfind("\n", 0, m.start()) + 1
            end = (text or "").find("\n", m.end())
            sentence = (text or "")[start:len(text) if end < 0 else end]
            # the subject of a clean claim is the verifier it names, never a file or a word in backticks
            subj = next((m.group(1) for m in _SUBJECT_RX.finditer(sentence) if is_test_runner(m.group(1))), None)
            return {"kind": kind, "subject": subj}
    return {}


def _rel(path: str, cwd: str) -> str:
    if cwd and os.path.isabs(path):
        try:
            rel = os.path.relpath(path, cwd)
            return path if rel.startswith("..") else rel
        except ValueError:
            return path
    return path


def fact_of(ev: dict, read: dict | None = None) -> dict:
    """One event as a fact; `read` is the ledger of every earlier seen file (relative to cwd)."""
    name = ev.get("hook_event_name", "")
    kind = _EVENT.get(name, name)
    cwd = ev.get("cwd") or ""
    tr = ev.get("tool_response")
    failed = name == "PostToolUseFailure" or (isinstance(tr, dict) and str(
        tr.get("exitCode", tr.get("returncode", 0)) or 0) not in ("0", ""))
    output = ev.get("last_assistant_message") if kind == "Stop" else response_text(ev)
    fact = {"event": kind, "tool": ev.get("tool_name"), "args": ev.get("tool_input") or {},
            "exit": (1 if failed else 0) if kind == "Post" else None, "output": output or "",
            "cwd": cwd, "source": {"read": dict(read or {})}}
    p = _path_of(ev)
    if p:
        fact["path"] = _rel(p, cwd)
    cmd = command_of(ev)
    if cmd:
        fact["args"] = {**fact["args"], "command": cmd}
    fact["claim"] = {"kind": "question", "subject": None} if ev.get("tool_name") == "AskUserQuestion" \
        else read_claim(output) if kind == "Stop" else {}
    return fact


def _suffixes(path: str, cwd: str) -> list:
    """Every trailing run of the path's components, so `tools/x.py`, cited from any directory,
    finds the file seen as `/home/u/repo/tools/x.py`."""
    full = os.path.normpath(path if os.path.isabs(path) else os.path.join(cwd or ".", path))
    parts = [p for p in full.split(os.sep) if p]
    return [full] + ["/".join(parts[i:]) for i in range(len(parts))]


def facts_of(events: list) -> list:
    """Facts for decoded events in record order, each carrying the ledger as of before it."""
    out, read = [], {}
    for ev in events:
        if not isinstance(ev, dict):
            continue
        out.append(fact_of(ev, read))
        seen = ev.get(SEEN_KEY)
        for path, h in (seen.items() if isinstance(seen, dict) else ()):
            for key in _suffixes(path, ev.get("cwd") or ""):
                read[key] = h
    return out
