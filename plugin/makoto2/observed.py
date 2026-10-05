"""R: the observed record. Settled history -> Record.

The only reader of tool responses for "was X observed". One settled hook event (PostToolUse or
PostToolUseFailure) becomes exactly one Obs; nothing else does. A PreToolUse row is a call that
may never have landed, so it observes nothing.

observed(objects, before) holds iff some Obs with seq < before executed (a result came back) and
named, wrote or created one of `objects`. Program names never decide it: the question is only
which objects an executed event touched.

Objects are paths and identifiers, normalised the same way on both sides:
  - a path-shaped token (holds a "/", or is name.ext) or a Bash operand word, joined onto the
    event's cwd when relative, then posixpath.normpath'd; a trailing ":line[:col]" is dropped;
  - a URL, kept verbatim;
  - a result count: a ratio "8/8", or "<n> passed|failed|skipped|error|..." lowercased.
Equality is exact: observing a directory does not observe the files under it, nor the reverse
(`ls src/` observes the entries it printed, not every file below src/).

Deterministic, stdlib only, no imports from any other package. The shell splitter is a copy of
Makoto 3.4.19 core/_shell.py `_shell_segments` (prior art), trimmed to what this module reads.
"""
from __future__ import annotations
from types import MappingProxyType

import copy
import functools
import json
import os
import posixpath
import re
import shlex
from typing import Iterable, NamedTuple, Optional

__all__ = ["Obs", "Record", "record"]

_SETTLED = ("PostToolUse", "PostToolUseFailure")


class Obs(NamedTuple):
    seq: int            # position in the history given to record()
    tool: str           # tool_name
    input: dict         # tool_input
    output: str         # tool_response flattened to text ("" if none)
    exit: Optional[int] # exit code when known, else None
    failed: bool        # PostToolUseFailure or is_error or a hook denial
    objects: frozenset  # paths and identifiers named in input or output (normalised)
    written: frozenset  # paths whose bytes this event changed
    created: frozenset  # paths this event brought into existence
    send: str           # text sent to a person or another session, else ""
    search: Optional[tuple]  # (scope, query, empty: bool) for ls/find/grep/env|cut/Glob/Grep


# ---- shell splitting (copied from Makoto 3.4.19 core/_shell.py, prior art) --------------------

_SHELL_SEPARATORS = frozenset({"|", "||", "&&", ";", "&", "\n"})
_ASSIGNMENT_RX = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.DOTALL)
_LAUNCH_WRAPPERS = frozenset({"command", "nohup", "sudo", "env", "timeout", "time", "stdbuf",
                              "xargs"})
_TIMEOUT_DURATION_RX = re.compile(r"\d+(?:\.\d+)?[smhd]?")
_NESTED_SHELL_PROGRAMS = frozenset({"ssh", "sh", "bash", "zsh"})
_SUDO_VALUED_OPTIONS = frozenset({"-u", "-g", "-h", "-p", "-r", "-t", "-C", "--user", "--group",
                                  "--host", "--prompt", "--role", "--type", "--close-from"})
_CONTROL_RUN_RX = re.compile(r"[|;&]+")
_HEAD_SUBSTITUTION_RX = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_]*=)?(?:\$\((?!\()|`)")


def _basename(word: str) -> str:
    return word.rsplit("/", 1)[-1]


def _effective_argv(argv):
    """Strip leading assignments and transparent launch wrappers."""
    argv = list(argv)
    while argv and _ASSIGNMENT_RX.fullmatch(argv[0]):
        argv.pop(0)
    while argv and _basename(argv[0]) in _LAUNCH_WRAPPERS:
        wrapper = _basename(argv.pop(0))
        while argv and (argv[0].startswith("-") or _ASSIGNMENT_RX.fullmatch(argv[0])):
            option = argv.pop(0)
            if wrapper == "sudo" and option in _SUDO_VALUED_OPTIONS and argv:
                argv.pop(0)
        if wrapper == "timeout" and argv and _TIMEOUT_DURATION_RX.fullmatch(argv[0]):
            argv.pop(0)
    return argv


def _normalize_segment_argv(argv):
    argv = [t for t in argv if t not in ("(", ")")]
    if not argv:
        return argv
    m = _HEAD_SUBSTITUTION_RX.match(argv[0])
    if m and len(argv[0]) > m.end():
        argv[0] = argv[0][m.end():]
        closer = "`" if m.group(0).endswith("`") else ")"
        for i, tok in enumerate(argv):
            if tok.endswith(closer):
                argv[i] = tok[:-1]
                break
    if argv[0].startswith("("):
        argv[0] = argv[0].lstrip("(")
    if argv and argv[-1].endswith(")"):
        argv[-1] = argv[-1].rstrip(")")
    return [t for t in argv if t]


def _nested_command(effective):
    """The command a shell or ssh word runs (`bash -c CMD`, `ssh host CMD`), else None."""
    if not effective or _basename(effective[0]) not in _NESTED_SHELL_PROGRAMS:
        return None
    if _basename(effective[0]) == "ssh":
        positional = [a for a in effective[1:] if not a.startswith("-")]
        return " ".join(positional[1:]) if len(positional) > 1 else None
    pos = effective.index("-c", 1) if "-c" in effective[1:] else len(effective)
    return effective[pos + 1] if pos + 1 < len(effective) else None


@functools.lru_cache(maxsize=4096)
def _segments(command: str):
    """((argv, following_operator), ...) for the literal statements of `command`; a heredoc body
    fed to a non-shell program is data and is skipped; () when it does not tokenize."""
    try:
        lexer = shlex.shlex(command or "", posix=True, punctuation_chars="|;&<>\n")
        lexer.whitespace_split = True
        lexer.commenters = ""
        lexer.whitespace = " \t\r"
        tokens = list(lexer)
    except (TypeError, ValueError):
        return ()
    segments, current = [], []

    def close_segment(operator):
        argv = _normalize_segment_argv(current)
        if argv:
            segments.append((argv, operator))
        current.clear()

    pending, active, suppress, expect, in_comment, at_start = [], None, True, False, False, True
    for i, token in enumerate(tokens):
        newline = token == "\n"
        if active is not None:
            if at_start and token == active and (i + 1 >= len(tokens) or tokens[i + 1] == "\n"):
                active = pending.pop(0) if pending else None
            at_start = newline
            continue
        at_start = newline
        if in_comment and not newline:
            continue
        in_comment = False
        if token.startswith("#") and not newline:
            in_comment = True
            continue
        if expect and not newline and token not in _SHELL_SEPARATORS:
            pending.append(token)
            expect = False
            current.append(token)
            if _basename((_effective_argv(current) or [""])[0]) in _NESTED_SHELL_PROGRAMS:
                suppress = False
            continue
        if token == "<<":
            expect = True
            current.append(token)
            continue
        if not (token in _SHELL_SEPARATORS or _CONTROL_RUN_RX.fullmatch(token)):
            current.append(token)
            continue
        close_segment(token)
        if newline and pending:
            active = pending.pop(0) if suppress else None
            pending[:] = pending if suppress else []
            suppress = True
    close_segment("")

    expanded = []
    for argv, operator in segments:
        command_ = _nested_command(_effective_argv(argv))
        nested = [list(x) for x in _segments(command_)] if command_ else []
        if nested:
            nested[-1] = [nested[-1][0], operator]
            expanded.extend((tuple(a), op) for a, op in nested)
            continue
        expanded.append((tuple(argv), operator))
    return tuple(expanded)


# ---- normalisation ----------------------------------------------------------------------------

_URL_RX = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s'\"<>()\[\]{}`]+", re.I)
_RATIO_RX = re.compile(r"(?<![\w/.])\d+/\d+(?![\w/.])")
_COUNT_RX = re.compile(r"\b(\d+)\s+(passed|failed|skipped|error|xfailed|xpassed|deselected|"
                       r"warning)s?\b", re.I)
_PASSED_N_RX = re.compile(r"\b(passed|failed)\s+(\d+)(?:/\d+)?\b", re.I)
# A path: segments joined by "/" (optionally rooted, ~ or ./ ../), or a bare name.ext. A dotted
# name directly followed by "(" or "[" is a call or an index in code (json.load(), d.items[), not
# a file, so it is not read as one.
_PATH_RX = re.compile(
    r"(?<![\w.@+~/-])(?:~|\.{1,2})?/?(?:[\w.@+-]+/)+[\w.@+*-]*"
    r"|(?<![\w.@+~/-])[\w@+*-]+(?:\.[\w@+*-]+)*\.[A-Za-z][A-Za-z0-9]{0,7}(?![\w(\[.])")
_LINE_REF_RX = re.compile(r"(?::\d+){1,2}$")
_EDGE_PUNCT = "\"'`,;:()[]{}<>"


def _norm(token: str, cwd: str) -> str:
    """One object, normalised: quotes and edge punctuation off, a trailing :line[:col] off, ~
    expanded, joined onto `cwd` when relative (and cwd is absolute), normpath'd. "" when nothing
    is left."""
    t = _LINE_REF_RX.sub("", str(token or "").strip().strip(_EDGE_PUNCT).replace("\\", "/"))
    if not t or t == "-":
        return ""
    if _URL_RX.fullmatch(t) or _RATIO_RX.fullmatch(t):
        return t
    t = os.path.expanduser(t) if t.startswith("~") else t
    t = posixpath.join(cwd, t) if not t.startswith("/") and cwd.startswith("/") else t
    out = posixpath.normpath(t)
    return "" if out == "." else out


def _text_objects(text: str, cwd: str) -> set:
    """Every object named in free text (a command, a prompt, a tool's output)."""
    text = str(text or "")
    out = {m.group(0) for m in _URL_RX.finditer(text)}
    rest = _URL_RX.sub(" ", text)
    out.update(m.group(0) for m in _RATIO_RX.finditer(rest))
    out.update(f"{m.group(1)} {m.group(2).lower()}" for m in _COUNT_RX.finditer(rest))
    out.update(f"{m.group(2)} {m.group(1).lower()}" for m in _PASSED_N_RX.finditer(rest))
    out.update(_norm(m.group(0), cwd) for m in _PATH_RX.finditer(_RATIO_RX.sub(" ", rest)))
    out.discard("")
    return out


# ---- reading one event ------------------------------------------------------------------------

_DENIAL_RX = re.compile(
    r"hook (?:error|denied|blocked)|blocked by (?:a )?hook|doesn't want to proceed|"
    r"tool use was rejected|permission (?:to use \S+ )?(?:was |has been )?denied", re.I)
_EXIT_RX = re.compile(r"\bexit(?:ed with)? (?:code|status) (-?\d+)", re.I)
_OUTPUT_KEYS = ("stdout", "stderr", "output", "error", "result", "content", "text", "message")
_SEND_TOOL_SUFFIXES = ("reply", "post_message", "message_thread", "start_thread_session")
_SEND_TOOLS = frozenset({"SendMessage", "Agent", "Task"})
_SEND_KEYS = ("text", "message", "prompt", "body", "content")
_PATH_KEYS = ("file_path", "notebook_path", "path", "filePath")
_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_REDIRECT_RX = re.compile(r"^[0-9]*&?>{1,2}\|?$")          # >, >>, 2>, &>, >|, &>>
_OPEN_WRITE_RX = re.compile(r"""open\(\s*['"]([^'"]+)['"]\s*,\s*['"][^'"]*[wax]""")
_WRITE_TEXT_RX = re.compile(r"""Path\(\s*['"]([^'"]+)['"]\s*\)\s*\.write_(?:text|bytes)\(""")


def _flatten(value) -> str:
    """A tool response as text: a string as-is; a dict by its output keys (and a Read's file
    content, a Glob/Grep's filenames); a list of content blocks by their text; else ""."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(filter(None, (_flatten(v) for v in value)))
    if not isinstance(value, dict):
        return ""
    parts = [_flatten(value.get(k)) for k in _OUTPUT_KEYS]
    f = value.get("file")
    parts.append(_flatten(f.get("content")) if isinstance(f, dict) else "")
    names = value.get("filenames")
    parts.append("\n".join(str(n) for n in names) if isinstance(names, list) else "")
    return "\n".join(p for p in parts if p)


def _exit_of(tr, output: str) -> Optional[int]:
    for k in ("exitCode", "exit_code", "returncode", "exit"):
        v = tr.get(k) if isinstance(tr, dict) else None
        if isinstance(v, int) and not isinstance(v, bool):
            return v
    m = _EXIT_RX.search(output or "")
    return int(m.group(1)) if m else None


def _executed(o: Obs) -> bool:
    """A result came back: an exit code is known, or the call did not fail, or it failed with
    output that is not a denial (a red run is still a run)."""
    if _DENIAL_RX.search(o.output):
        return False
    if o.exit is not None or not o.failed:
        return True
    return bool(o.output.strip()) and not _DENIAL_RX.search(o.output)


# What each writing program writes, as (words, plain operands) -> (written, maybe-new, created).
# A program not in the table writes nothing it names; that is the table's whole default.
def _w_mkdir(words, plain):
    return (), (), plain


def _w_touch(words, plain):
    return plain, plain, ()


def _w_tee(words, plain):
    appends = "-a" in words or "--append" in words
    return plain, (() if appends else plain), ()


def _w_copy(words, plain):
    return (plain[-1:], plain[-1:], ()) if len(plain) >= 2 else ((), (), ())


def _w_truncate(words, plain):
    return plain, (), ()


def _w_inplace(words, plain):
    if not any(w.startswith(("-i", "-pi")) for w in words):
        return (), (), ()
    return (plain if "-e" in words else plain[1:]), (), ()


def _w_none(words, plain):
    return (), (), ()


_WRITERS = {"mkdir": _w_mkdir, "touch": _w_touch, "tee": _w_tee, "cp": _w_copy, "mv": _w_copy,
            "install": _w_copy, "truncate": _w_truncate, "sed": _w_inplace, "perl": _w_inplace}


# Search programs as (argv, plain operands) -> (scope, query). Not in the table: not a search.
def _s_ls(argv, plain):
    return (plain[0] if plain else "."), ""


def _s_find(argv, plain):
    query = next((argv[k + 1] for k, w in enumerate(argv[:-1])
                  if w in ("-name", "-iname", "-path", "-regex")), "")
    return (plain[0] if plain else "."), query


def _s_grep(argv, plain):
    return (plain[1] if len(plain) > 1 else "."), (plain[0] if plain else "")


_SEARCHES = {"ls": _s_ls, "find": _s_find, "grep": _s_grep, "egrep": _s_grep, "fgrep": _s_grep,
             "rg": _s_grep}
_ENV_CUT_RX = re.compile(r"(?:^|[|;&\s])env\s*\|[^\n]*\bcut\b")


def _search_of(program, argv, plain, cwd, output, command):
    """((scope, query, empty) or None, the entries a listing printed) for one statement."""
    if program == "cut" and _ENV_CUT_RX.search(command):
        return ("env", "", not output.strip()), set()
    reader = _SEARCHES.get(program)
    if reader is None:
        return None, set()
    scope, query = reader(argv, plain)
    base = _norm(scope, cwd) or scope
    lines = [ln.strip() for ln in output.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("total ") and not ln.endswith(":")]
    entries = ({_norm(posixpath.join(base, ln.split()[-1]), "") for ln in lines}
               if program == "ls" else
               {_norm(ln, cwd) for ln in lines} if program == "find" else set())
    return (base, query, not output.strip()), entries


def _bash_reading(command: str, cwd: str, output: str):
    """(objects, written, maybe-new, created, search) of one Bash command."""
    objects, written, maybe_new, created = set(), set(), set(), set()
    search = None
    for argv, _op in _segments(command):
        argv = _effective_argv(list(argv))
        if not argv:
            continue
        program = _basename(argv[0])
        words, skip = [], False
        for i, w in enumerate(argv[1:], 1):
            nxt = argv[i + 1] if i + 1 < len(argv) else ""
            if skip:
                skip = False
                continue
            skip = w in ("<<", "<<<", "<<-", "<", ">&", "<&") or bool(_REDIRECT_RX.match(w))
            objects.update((_norm(nxt, cwd),) if w == "<" else ())
            target = bool(_REDIRECT_RX.match(w)) and bool(nxt) and not nxt.isdigit() \
                and nxt != "-" and not nxt.startswith(("/dev/", "&"))
            written.update((_norm(nxt, cwd),) if target else ())
            maybe_new.update((_norm(nxt, cwd),) if target and ">>" not in w else ())
            words.extend(() if skip else (w,))
        operands = [w for w in words if not w.startswith("-") and not w.isdigit()
                    and "$" not in w and "`" not in w]
        texts = [w for w in operands if any(c.isspace() for c in w)]
        plain = [w for w in operands if w not in texts]
        for w in texts:
            objects.update(_text_objects(w, cwd))           # a quoted text argument
        objects.update(_norm(w, cwd) for w in plain)
        w_, m_, c_ = _WRITERS.get(program, _w_none)(words, [_norm(p, cwd) for p in plain])
        written.update(w_)
        maybe_new.update(m_)
        created.update(c_)
        found, entries = _search_of(program, argv, plain, cwd, output, command)
        search = search or found
        objects.update(entries)
    # the command's full text (heredoc bodies and quoted code included) names objects too
    objects.update(_text_objects(command, cwd))
    for rx in (_OPEN_WRITE_RX, _WRITE_TEXT_RX):
        for m in rx.finditer(command):
            written.add(_norm(m.group(1), cwd))
            maybe_new.add(_norm(m.group(1), cwd))
    for s in (objects, written, maybe_new, created):
        s.discard("")
    return objects | written | created, written, maybe_new, created, search


def _value_objects(key, value, cwd: str) -> set:
    """The objects one tool_input value names: a path key is one path; text is scanned; a list
    or dict is read item by item; anything else names nothing."""
    if isinstance(value, dict):
        return _input_objects(value, cwd)
    if isinstance(value, list):
        return set().union(*(_value_objects("", v, cwd) for v in value)) if value else set()
    if not isinstance(value, str) or key == "command":
        return set()
    return {_norm(value, cwd)} if key in _PATH_KEYS else _text_objects(value, cwd)


def _input_objects(ti: dict, cwd: str) -> set:
    out = set().union(*(_value_objects(k, ti[k], cwd) for k in sorted(ti))) if ti else set()
    out.discard("")
    return out


def _read(ev: dict, seq: int, seen: set) -> Obs:
    tool = str(ev.get("tool_name") or "")
    ti = ev.get("tool_input") if isinstance(ev.get("tool_input"), dict) else {}
    cwd = str(ev.get("cwd") or "")
    tr = ev.get("tool_response")
    trd = tr if isinstance(tr, dict) else {}
    output = "\n".join(p for p in (_flatten(tr), _flatten(ev.get("error"))) if p)
    exit_ = _exit_of(tr, output)
    failed = (ev.get("hook_event_name") == "PostToolUseFailure"
              or bool(trd.get("is_error") or trd.get("isError") or trd.get("interrupted"))
              or bool(_DENIAL_RX.search(output)))
    objects = _input_objects(ti, cwd)
    written, created, search = set(), set(), None
    command = ti.get("command")
    if isinstance(command, str) and command:
        o, w, maybe_new, c, search = _bash_reading(command, cwd, output)
        objects |= o
        written |= w
        created |= c | {p for p in maybe_new if p not in seen}
    p = _norm(ti.get("file_path") or ti.get("notebook_path") or "", cwd) \
        if tool in _WRITE_TOOLS else ""
    kind = trd.get("type")
    written |= {p} if p else set()
    created |= {p} if p and tool == "Write" and (
        kind == "create" or (kind is None and p not in seen)) else set()
    if tool in ("Glob", "Grep"):
        scope = _norm(ti.get("path") or cwd or ".", cwd) or "."
        names = trd.get("filenames")
        empty = (not output.strip()) or output.strip() in ("No files found", "No matches found") \
            or trd.get("numFiles") == 0
        search = (scope, str(ti.get("pattern") or ""), bool(empty))
        objects.update(_norm(str(n), cwd) for n in (names if isinstance(names, list) else ()))
    objects |= _text_objects(output, cwd) | written | created
    objects.discard("")
    sends = tool in _SEND_TOOLS or tool.endswith(_SEND_TOOL_SUFFIXES)
    send = "\n".join(ti[k] for k in _SEND_KEYS if isinstance(ti.get(k), str) and ti[k]) \
        if sends else ""
    observation = Obs(seq=seq, tool=tool, input=dict(ti), output=output, exit=exit_, failed=failed,
               objects=frozenset(objects), written=frozenset(written), created=frozenset(created),
               send=send, search=search)
    # Keep the attempted input for retry detection, but a denied/unlanded call has no deeds.
    if not _executed(observation):
        observation = observation._replace(written=frozenset(), created=frozenset(),
                                           send="", search=None)
    return observation


# ---- the record -------------------------------------------------------------------------------

class Record:
    """The settled history as observations, oldest first."""

    def __init__(self, obs: Iterable[Obs] = (), turn_start: int = 0, user_texts=()):
        self.obs = list(obs)
        self.turn_start = turn_start        # seq of the first Obs after the last turn boundary
        self.user_texts = list(user_texts)  # user messages observed, oldest first

    def observed(self, objects: Iterable[str], before: Optional[int] = None) -> bool:
        """Some settled Obs before `before` (by seq) that executed names, wrote or created any
        of `objects`. Pass objects as objects_of() gives them; each is also tried normalised
        without a cwd."""
        wanted = set()
        for x in objects or ():
            wanted.update((str(x), _norm(x, "")) if x else ())
        wanted.discard("")
        for o in self.obs:
            if before is not None and o.seq >= before:
                break
            if _executed(o) and wanted & (o.objects | o.written | o.created):
                return True
        return False

    def objects_of(self, event: dict) -> frozenset:
        """The objects a not-yet-settled event names in its input, normalised as Obs.objects."""
        if not isinstance(event, dict):
            return frozenset()
        ti = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
        cwd = str(event.get("cwd") or "")
        out = _input_objects(ti, cwd)
        command = ti.get("command")
        out |= _bash_reading(command, cwd, "")[0] if isinstance(command, str) and command else set()
        out.discard("")
        return frozenset(out)


_TURN_MARKS = ("UserPromptSubmit", "Stop", "SubagentStop")
_FETCH_TOOL_SUFFIXES = ("fetch_thread", "fetch_messages", "fetch_project_timeline")
_MESSAGE_TEXT_KEYS = ("body", "text", "content", "message")


def _user_entries(value) -> list:
    """Texts of every entry authored by "user" in a fetch tool's response, in order. A string
    response is read as JSON when it parses; anything else yields nothing."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if isinstance(value, list):
        return [t for v in value for t in _user_entries(v)]
    if not isinstance(value, dict):
        return []
    if value.get("author") == "user":
        text = next((value[k] for k in _MESSAGE_TEXT_KEYS if isinstance(value.get(k), str)), "")
        return [text] if text else []
    return [t for k in sorted(value) for t in _user_entries(value[k])]


def record(events: Iterable[dict], event: Optional[dict] = None) -> Record:
    """events = decoded hook payloads, oldest first; settled ones become Obs, with seq = the
    event's position in `events` (so `before` can be the act's own position in the same list).
    Stop and UserPromptSubmit events are not Obs; they mark turns (Record.turn_start) and a
    prompt's text joins Record.user_texts, as do user-authored entries of a fetched thread.
    An optional current event follows the history only when settled; pending calls and current
    turn boundaries cannot become witnesses or erase the turn being evaluated."""
    events = list(events or ())
    if isinstance(event, dict) and event.get("hook_event_name") in _SETTLED:
        events.append(event)
    events = tuple(copy.deepcopy(tuple(events)))
    obs, seen, users, boundary = [], set(), [], None
    readers = {}
    for i, ev in enumerate(events or ()):
        name = ev.get("hook_event_name") if isinstance(ev, dict) else None
        if name in _TURN_MARKS:
            boundary = i
            prompt = ev.get("prompt") if name == "UserPromptSubmit" else None
            users.extend((prompt,) if isinstance(prompt, str) and prompt else ())
            continue
        if name not in _SETTLED:
            continue
        o = _read(ev, i, seen)
        obs.append(o)
        readers[i] = MappingProxyType({"cwd": str(ev.get("cwd") or ""),
                                      "source_reads": tuple(ev.get("source_reads") or ())})
        if _executed(o):
            seen |= o.objects
        fetched = o.tool.endswith(_FETCH_TOOL_SUFFIXES) and _executed(o)
        users.extend(_user_entries(ev.get("tool_response")) if fetched else ())
    rec = Record(obs)
    rec.events = events
    rec.reader_evidence = MappingProxyType(readers)
    rec.user_texts = users
    rec.turn_start = 0 if boundary is None else next(
        (o.seq for o in obs if o.seq > boundary), boundary + 1)
    return rec


# ---------- what kind of act an event is (one definition; rows gate on these, never on tool names) ----------
_SAY_SUFFIXES = ("reply", "post_message")               # text to a person
_THREAD_SUFFIX, _NOTE_SUFFIX = "start_thread_session", "message_thread"


def act_kinds(event: dict) -> frozenset:
    """say (to a person, including the turn's closing text), brief (to another session), thread, note,
    write, run. Derived from the same send/write definitions Obs uses."""
    if event.get("hook_event_name") in ("Stop", "SubagentStop"):
        return frozenset({"say"})
    tool = str(event.get("tool_name") or "")
    kinds = set()
    if tool.endswith(_SAY_SUFFIXES):
        kinds.add("say")
    if tool in _SEND_TOOLS or tool.endswith((_THREAD_SUFFIX, _NOTE_SUFFIX)):
        kinds.add("brief")
    if tool.endswith(_THREAD_SUFFIX):
        kinds.add("thread")
    if tool.endswith(_NOTE_SUFFIX):
        kinds.add("note")
    if tool in _WRITE_TOOLS:
        kinds.add("write")
    if tool == "Bash":
        kinds.add("run")
    return frozenset(kinds)


def text_of(event: dict) -> str:
    """The words an act puts out: the closing message at Stop, else every send key of the input."""
    if event.get("hook_event_name") in ("Stop", "SubagentStop"):
        return str(event.get("last_assistant_message") or "")
    ti = event.get("tool_input") or {}
    return "\n".join(ti[k] for k in _SEND_KEYS if isinstance(ti.get(k), str) and ti[k]) if isinstance(ti, dict) else ""
