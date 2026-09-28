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
import stat

from makoto.core._shell import statements
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
    """The file's hash, or None: only a regular file under the size cap is read, so a FIFO or a
    device a call names can never block the hook."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    except (OSError, ValueError, TypeError):
        return None                      # a NUL in the path, a missing file, no permission
    try:
        st = os.fstat(fd)                # the descriptor, not the name: no swap between the two
        if not stat.S_ISREG(st.st_mode) or st.st_size > _MAX_HASHED:
            return None
        with os.fdopen(fd, "rb") as f:
            fd = None
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except OSError:
        return None
    finally:
        if fd is not None:
            os.close(fd)


def _seen_paths(payload: dict) -> list:
    """The files a settled call showed the session: a Read/Write/Edit's path, or every argument of a
    Bash command that names an existing file (`cat`, `sed -n`, `grep ... file`)."""
    if payload.get("tool_name") in _SEEING_TOOLS:
        p = _path_of(payload)
        return [p] if p else []
    if payload.get("tool_name") == "Bash":
        stmts = statements(command_of(payload) or "")
        if stmts is None:
            return []
        cwds, out = {(): payload.get("cwd") or "."}, []
        for words, scope, _before in stmts[:64]:
            for i in range(1, len(scope) + 1):  # a subshell starts in its parent's directory
                cwds.setdefault(scope[:i], cwds[scope[:i - 1]])
            if words[0] == "cd":
                dest = [w for w in words[1:] if w != "--"][:1]
                if dest:
                    cwds[scope] = dest[0] if os.path.isabs(dest[0]) else os.path.join(cwds[scope], dest[0])
                continue
            for w in words[1:]:
                if w.startswith("-"):
                    continue
                full = w if os.path.isabs(w) else os.path.join(cwds[scope], w)
                try:
                    if os.path.isfile(full):
                        out.append(full)
                except ValueError:
                    pass
        return out
    return []


def stamp(payload: dict) -> dict | None:
    """The payload with {path: hash} of each file it showed the session, for a settled call; else None."""
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if payload.get("hook_event_name") != "PostToolUse" or ti.get("run_in_background"):
        return None                      # a background launch has read nothing yet
    cwd = payload.get("cwd") or "."
    seen = {}
    for p in _seen_paths(payload):
        h = file_hash(p if os.path.isabs(p) else os.path.join(cwd, p))
        if h is not None:
            seen[p] = h
    return {**payload, SEEN_KEY: seen} if seen else None


_QUOTED_RX = _lazy_re(r'"[^"\n]*"|“[^”\n]*”')
_FENCED_RX = _lazy_re(r"```.*?(?:```|\Z)", re.S)
_SENTENCES_RX = _lazy_re(r"(?<=[.!?])\s+|\n+")


def read_claim(text: str) -> dict:
    """{kind, subject} of the first claim sentence in `text`, by the word table; {} for none. A
    quoted sentence is not the writer's; a sentence ending in `?` is a question and nothing else;
    the subject is a runner command named in the same sentence."""
    prose = _FENCED_RX.sub(" ", text or "")     # an example in a fence claims nothing
    for sentence in _SENTENCES_RX.split(_QUOTED_RX.sub(" ", prose)):
        if not sentence.strip():
            continue
        if sentence.rstrip().endswith("?"):
            return {"kind": "question", "subject": None}
        for kind, rx in CLAIM_WORDS.items():
            if kind != "question" and _claim(sentence, rx) is not None:
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


def _view(read: dict, cwd: str) -> dict:
    """{key: hash} as seen from `cwd`: a relative key that names a different existing file here
    is some other file, never the one seen."""
    out = {}
    for key, (full, h) in read.items():
        if not os.path.isabs(key) and cwd:
            here = os.path.normpath(os.path.join(cwd, key))
            if here != full and os.path.exists(here):
                continue
        out[key] = h
    return out


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
            "cwd": cwd, "source": {"read": _view(read or {}, cwd)}}
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
            keys = _suffixes(path, ev.get("cwd") or "")
            for key in keys:
                read[key] = (keys[0], h)
    return out
