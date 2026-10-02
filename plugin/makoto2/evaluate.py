"""V: the one evaluator. Rows (W) x Record (R) x current event -> block dict or None.

Stdlib only, no makoto imports. `record` is R from CANOPY.md "Fixed interface of R" (`.obs`,
`.observed`, `.objects_of`). Two optional attributes are read with getattr and default to "not
known": `turn_start` (seq of the last user prompt; absent -> the whole record is the turn) and
`user_texts` (texts of observed user messages). Neither is in R's fixed interface.

Each row is a pair: owes(event) -> the subjects the act commits to, pays(obs) -> a predicate over
subjects that one observed effect witnesses (effects from R, never command names). evaluate() runs
`unwitnessed` over R's settled Obs plus the current event and blocks on the first unpaid subject.
Outcome is binary: {"row", "message", "objects"} blocks, None is silent.
"""
from __future__ import annotations

import csv
import json
import os
import re
import xml.etree.ElementTree as ET
from makoto2.lineage import unpaid as lineage_unpaid
from makoto2 import family_spec, family_lineage, family_switch
from makoto2.family_other import findings as other_findings
from typing import Optional


# Copied verbatim from Makoto plugin/makoto/kit.py lines 536-561 (Clear-Sights/Makoto a56f0b2).
def unwitnessed(events, *, owes, pays=None, paid=()):
    """The one shape: an event owes a witness, and only an earlier event can pay it.

    `owes(ev)` gives the subjects `ev` commits to; `pays(ev)` gives a predicate over subjects
    that `ev` witnesses, or None. Yields `(ev, subject)` for every subject nothing up to it
    paid. `paid` seeds predicates that hold before the first event, for a caller whose witness
    is the whole record rather than one event of it. A witness pays its own event and every
    later one, never an earlier one. One pass; a predicate that pays everything
    short-circuits, so an obligation stays O(events).

    `pays` defaults to None -- no per-event witness at all -- for the callers whose witnesses are
    seeded whole via `paid` (a prior tool response, the whole session's own record, the operator-
    turn ledger). A caller with nothing to add here need not write its own always-None function.

    The register's families differ only in what counts as the witness: none can pay a held
    wrong form (SPEC), a second reading of the subject (THE OTHER POINT), an act that selected
    the branch (THE SWITCH), a read of the source before the write (THE LINEAGE).
    """
    paid = list(paid)
    for ev in events:
        p = pays(ev) if pays is not None else None
        if p is not None:
            paid.append(p)
        for subject in owes(ev) or ():
            if not any(q(subject) for q in paid):
                yield ev, subject


# ---------- rows ----------

def load_rows(path: str, cfg: dict, *, pins_path: Optional[str] = None) -> list:
    """Load rows with verbatim quote agreement against the current source fixture.

    The default fixture is tests/sources.tsv in this checkout; callers with a
    separately packaged fixture may select it explicitly. Agreement certifies
    only these fixture bytes, never the historical source's provenance. The
    optional words= path is carried through without reading or creating it.
    Both files are reread on every call; absent or invalid pins reject the rows.
    """
    if pins_path is None:
        pins_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "..", "tests", "sources.tsv")

    tables = []
    for filename, required in (
            (pins_path, ("id", "found_in", "quote")),
            (path, ("id", "moment", "predicate", "args", "source"))):
        with open(filename, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)) or not set(required) <= set(fields):
                raise ValueError(f"{filename}: missing or duplicate columns")
            table = list(reader)
        ids = set()
        for row in table:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{filename}: malformed row")
            if not row["id"] or row["id"] in ids:
                raise ValueError(f"{filename}: empty or duplicate id")
            ids.add(row["id"])
        tables.append(table)

    pins = {row["id"]: row["quote"] for row in tables[0]}
    out = []
    for row in tables[1]:
        source = row["source"]
        prefix, separator, quote = source.partition(': "')
        if (not prefix or not separator or not quote.endswith('"')
                or not quote[:-1] or pins.get(row["id"]) != quote[:-1]):
            raise ValueError(f"{path}: missing or mismatched source pin for {row['id']}")
        args = {}
        for part in filter(None, row.get("args", "").split(";")):
            k, _, v = part.partition("=")
            args[k.strip()] = v.strip()
        row["args"] = args
        row["cfg"] = cfg
        out.append(row)
    return out


def load_cfg(path: str) -> dict:
    """Read runtime defaults and resolve the documented state-directory override.

    Read on every call so changed configuration and environment are current.
    Other values, including additional JSON keys, pass through unchanged.
    """
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    if not isinstance(cfg, dict):
        raise ValueError("configuration must be a JSON object")
    state_dir = os.environ.get("MAKOTO_STATE_DIR") or cfg.get("state_dir")
    if state_dir is not None:
        cfg["state_dir"] = os.path.expanduser(state_dir)
    return cfg


def _load_r():
    import importlib.util
    spec = importlib.util.spec_from_file_location("makoto2_observed", os.path.join(os.path.dirname(os.path.abspath(__file__)), "observed.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_R = _load_r()


def _acts(args):
    return set(filter(None, args.get("acts", "").split(",")))


def evaluate(rows, record, event) -> Optional[dict]:
    """First row whose moment matches the event and has an unpaid subject -> block; else None."""
    moment = event.get("hook_event_name", "")
    cfg = rows[0].get("cfg", {}) if rows else {}
    for finding in family_spec.evaluate(record, event, cfg):
        return finding
    if moment in ("PreToolUse", "Stop", "SubagentStop"):
        if family_lineage.lineage_absence(record, event, _R):
            return {"row": "R05", "message": "claim has no falsifier -- REGISTRY-v9.md:739 B32/C2", "objects": ["claim"]}
        for predicate, row, citation in (
            (family_lineage.lineage_edit, "L.edit", "REGISTRY-v9.md:495,782 F2/H3"),
            (family_lineage.lineage_units, "L.units", "REGISTRY-v9.md:814 H6"),
        ):
            subjects = predicate(record, event, _R)
            if subjects:
                return {"row": row, "message": citation, "objects": subjects}
        for state, name in lineage_unpaid(record, event, _R):
            return {"row": "R08", "message": f"R08 {state} source {name} -- source: REGISTRY-v9.md:13-16 H5/H2", "objects": [name]}
    cfg = rows[0].get("cfg", {}) if rows else {}
    for finding in other_findings(record, event, _R, cfg.get("dispatch", False)):
        return finding
    for finding in family_switch.findings(record,event,cfg):
        return finding
    for row in rows:
        if moment not in row["moment"].split(","):
            continue
        args, cfg = row.get("args") or {}, row.get("cfg") or {}
        if row["id"] in ("R05", "R07", "R12"):
            continue
        acts = _acts(args)
        dispatch_brief = (cfg.get("dispatch") and moment == "PreToolUse"
                          and event.get("tool_name") in ("Agent", "Task")
                          and row["id"] in DISPATCH_SPECS)
        if acts and not (acts & _R.act_kinds(event)) and not dispatch_brief:
            continue
        if row["id"] == "R08" and not dispatch_brief:
            continue
        spec = PREDICATES[row["predicate"]]
        if dispatch_brief:
            spec = DISPATCH_SPECS.get(row["id"], spec)
        subjects = spec.owes(args, cfg, record, event)
        if row["id"] == "R11" and moment == "Stop":
            subjects = [s for s in subjects if s[2] in ("acceptance", "artifact", "status")
                        or s[0] not in ("shipped", "pushed", "landed", "merged", "done", "fixed", "finished", "complete", "completed", "ready", "failed") ]
        if not subjects:
            continue
        paid = spec.seed(args, cfg, record) if spec.seed else ()
        # the current event is not settled: it owes, it never pays
        pays = (lambda o, _s=spec: None if o is event else _s.pays(args, cfg, o)) if spec.pays else None
        stream = list(record.obs) + [event]
        owes = lambda ev, _subj=subjects: _subj if ev is event else ()
        for _ev, subject in unwitnessed(stream, owes=owes, pays=pays, paid=paid):
            n = cfg["snippet_len"]
            return {"row": row["id"],
                    "message": (f"row {row['id']} ({row['predicate']}): {spec.why} "
                                f"[{str(subject)[:n]}] -- source: {row['source']}"),
                    "objects": [str(x) for x in (subject if isinstance(subject, (tuple, frozenset)) else (subject,))]}
    return None


class Spec:
    def __init__(self, owes, pays=None, seed=None, why=""):
        self.owes, self.pays, self.seed, self.why = owes, pays, seed, why


# Filled labels and path-attached pins reuse the dispatch grammar from 648f876.
def _brief_fields(event):
    prompt = (event.get("tool_input") or {}).get("prompt", "")
    fields = {k: [] for k in ("READ", "WRITE", "ACCEPTANCE")}
    if not isinstance(prompt, str):
        return fields
    label = None
    for line in prompt.splitlines():
        match = re.match(r"^(READ|WRITE|ACCEPTANCE):[ \t]*(.*)$", line)
        if match:
            label = match[1]
            if match[2].strip():
                fields[label].append(match[2].strip())
        elif label == "READ" and line.strip():
            fields[label].append(line.strip())
    return fields


def dispatch_schema_owes(args, cfg, record, event):
    if not cfg.get("dispatch") or event.get("tool_name") not in ("Agent", "Task"):
        return []
    return [k for k, values in _brief_fields(event).items() if not values]


def dispatch_pins_owes(args, cfg, record, event):
    return family_lineage.lineage_pin(args, cfg, record, event)


DISPATCH_SPECS = {
    "R04": Spec(dispatch_schema_owes, why="dispatch brief lacks a filled field"),
    "R08": Spec(dispatch_pins_owes, why="declared READ input lacks its revision pin"),
}


# ---------- shared readings ----------

# Tools whose output is another session's (agent-authored) text, not a primary observation.
OTHER_SESSION_TOOLS = frozenset({
    "mcp__hearthbot__fetch_thread", "mcp__hearthbot__fetch_messages",
    "mcp__hearthbot__fetch_project_timeline", "mcp__hearthbot__list_thread_sessions",
    "mcp__claude-code-remote__get_session", "mcp__claude-code-remote__list_events",
    "mcp__claude-code-remote__get_event", "Agent", "Task", "SendMessage",
})
_SOURCE_NAMED_RX = re.compile(r"\b(reports?|reported|says|said|claims?|claimed|per|according to|writes|wrote)\b", re.I)


def _text_of(event) -> str:
    return _R.text_of(event)


def _sentences(text: str) -> list:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _strip_quoted(text: str) -> str:
    """Drop code spans/blocks, quoted lines and double-quoted spans: words shown, not said."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(">"))
    return re.sub(r"[\"“][^\"”]*[\"”]", " ", text)


def _primary(o) -> bool:
    return o.tool not in OTHER_SESSION_TOOLS and not o.failed


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()


_LEAVES = (str, int, float, bool, type(None))


def _walk_user_texts(node, out):
    if isinstance(node, dict):
        if node.get("author") == "user":
            out.extend(node[k] for k in ("body", "text", "content") if isinstance(node.get(k), str))
        for v in node.values():
            _walk_user_texts(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_user_texts(v, out)
    elif isinstance(node, _LEAVES):
        return
    else:
        raise TypeError(f"not a JSON value: {type(node).__name__}")


def _user_texts_of(o) -> list:
    out = []
    try:
        _walk_user_texts(json.loads(o.output), out)
    except (ValueError, TypeError):
        return []
    return out


def _last_same_call(record, event):
    last = None
    for o in record.obs:
        if o.tool == event.get("tool_name") and o.input == (event.get("tool_input") or {}):
            last = o
    return last


def _names(o, path: str) -> bool:
    bare = path.lstrip("./")
    objs = set(o.objects) | set(o.written) | set(o.created)
    return any(x == path or x.endswith("/" + bare) or x == bare for x in objs)


def _is_act(args, o) -> bool:
    return bool(_acts(args) & _R.act_kinds({"tool_name": o.tool, "tool_input": o.input}))


_DENIAL_RX = re.compile(r"\b(denied|permission|blocked by|hook|not allowed|refused|deny)\b", re.I)


def _denied(o) -> bool:
    return o.failed and bool(_DENIAL_RX.search(o.output or ""))


# ---------- rows as (owes, pays) ----------

_ASK_PHRASE_RX = re.compile(
    r"\b(should i|shall i|do you want|would you like|want me to|let me know (?:if|whether|which)|"
    r"which (?:one )?do you prefer|can you confirm|please confirm|your call)\b", re.I)


def asks_owes(args, cfg, record, event):
    text = _strip_quoted(_text_of(event))
    m = _ASK_PHRASE_RX.search(text)
    if m:
        return [m.group(0)]
    return [s.strip() for s in _sentences(text) if s.rstrip().endswith("?")][:1]


def thread_owes(args, cfg, record, event):
    start = getattr(record, "turn_start", None) or 0
    prior = [o for o in record.obs if _is_act(args, o) and o.seq >= start and not o.failed]
    return [f"thread started at seq {prior[-1].seq}"] if prior else []


_TARGET_KEYS = ("session_id", "thread_id", "thread_ts", "thread", "to")


def _target(ti) -> str:
    return next((str(ti[k]) for k in _TARGET_KEYS if isinstance(ti, dict) and ti.get(k)), "")


def pile_owes(args, cfg, record, event):
    tgt = _target(event.get("tool_input") or {})
    sends = [o for o in record.obs if _is_act(args, o) and _target(o.input) == tgt and not o.failed]
    return [(tgt, sends[-1].seq)] if tgt and sends else []


def pile_pays(args, cfg, o):
    if o.tool not in OTHER_SESSION_TOOLS or _is_act(args, o) or o.failed or not o.output:
        return None
    return lambda s: s[0] in o.output and o.seq > s[1]


_ABSENCE_RXS = [
    re.compile(r"\bnot signed in(?: to| on)? (?:the )?([\w.\-/]+)", re.I),
    re.compile(r"([\w.\-/]+) (?:is|are|was|were) (?:still )?(?:missing|not installed|never applied|not there)\b", re.I),
    re.compile(r"([\w.\-/]+) (?:does not|doesn't|did not|didn't) exist\b", re.I),
    re.compile(r"\b(?:missing|not installed|never applied):\s*(?:the )?([\w.\-/]+)", re.I),
    re.compile(r"\b(?:there is|there's|there are|has|have|had) no ([\w.\-/]+)", re.I),
    re.compile(r"\bno such ([\w.\-/]+)", re.I),
    re.compile(r"\bno ([\w.\-/]+) (?:exists?|found|anywhere)\b", re.I),
]
_STOP_WORDS = frozenset({"it", "this", "that", "they", "the", "a", "an", "one", "thing", "file", "files",
                         "is", "he", "she", "you", "we", "i", "on", "in", "at", "to", "for", "of"})


_GENERIC_ABSENCE = 4          # _ABSENCE_RXS from this index on name no state, only 'no X'
_REPORTED_RX = re.compile(r"\b(?:said|says|told|claimed|claims|stated|reported|wrote)\b", re.I)
_SEARCHABLE_RX = re.compile(r"[/._\-\d]|^[A-Z0-9_]{3,}$|[a-z][A-Z]")


def absence_owes(args, cfg, record, event):
    things = []
    for sentence in _sentences(_strip_quoted(_text_of(event))):
        for i, rx in enumerate(_ABSENCE_RXS):
            for m in rx.finditer(sentence):
                if _REPORTED_RX.search(sentence[:m.start()]):
                    continue
                raw = m.group(1).strip(".,;:")
                if i >= _GENERIC_ABSENCE and not _SEARCHABLE_RX.search(raw):
                    continue
                things.append(raw.lower())
    return [t for t in things if t and t not in _STOP_WORDS]


def absence_pays(args, cfg, o):
    if o.search is None or not o.search[2] or o.failed:
        return None
    scope = (str(o.search[0]) + " " + str(o.search[1])).lower()
    return lambda thing: thing.rsplit("/", 1)[-1] in scope


_NUM_RX = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?%?|\d{1,3}(?:,\d{3})+)(?![\w.])")


def number_owes(args, cfg, record, event):
    # a subject only when the number is in another session's text (a relay), not merely unobserved
    other = [o.output or "" for o in record.obs if o.tool in OTHER_SESSION_TOOLS]
    out = []
    for s in _sentences(_text_of(event)):
        if _SOURCE_NAMED_RX.search(s):
            continue
        for m in _NUM_RX.finditer(s):
            n = m.group(1)
            if len(re.sub(r"\D", "", n)) >= cfg["min_number_digits"] or "." in n or "%" in n:
                out.append(n)
    return [n for n in out if any(re.search(r"(?<![\w.])" + re.escape(n) + r"(?![\w])", t) for t in other)]


def number_pays(args, cfg, o):
    if not _primary(o) or not o.output:
        return None
    return lambda n: re.search(r"(?<![\w.])" + re.escape(n) + r"(?![\w])", o.output) is not None


def _words_text(path: str) -> str:
    # A changed or removed optional fixture must invalidate its previous witness.
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return _norm(fh.read())
    except OSError:
        return ""


_ATTRIB_RX = re.compile(r"(his words|her words|the user(?:'s words)?|gabriel)\b\s*(?:said|wrote|asked|:|,|\()?", re.I)
_QUOTE_RX = re.compile(r"[\"“]([^\"”]+)[\"”]|^\s*>\s?(.+)$", re.M)


def quote_owes(args, cfg, record, event):
    text, out = _text_of(event), []
    for a in _ATTRIB_RX.finditer(text):
        q = _QUOTE_RX.search(text[a.end(): a.end() + cfg["quote_window"]])
        if not q or q.start() > cfg["quote_gap"]:
            continue
        quote = _norm(q.group(1) or q.group(2) or "").strip(" .")
        if len(quote) >= cfg["quote_min_len"]:
            out.append(quote)
    return out


def quote_seed(args, cfg, record):
    words = _words_text(args.get("words", ""))
    users = [_norm(t) for t in (getattr(record, "user_texts", None) or ())]
    return [lambda q: q in words or any(q in u for u in users)]


def quote_pays(args, cfg, o):
    if o.tool not in OTHER_SESSION_TOOLS:
        return None
    users = [_norm(t) for t in _user_texts_of(o)]
    return (lambda q: any(q in u for u in users)) if users else None


_PATH_RX = re.compile(r"(?<![\w@:/])((?:~|\.{1,2})?/?(?:[\w.\-]+/)+[\w.\-]+\.[A-Za-z0-9]+|/(?:[\w.\-]+/)+[\w.\-]+)")


def write_owes(args, cfg, record, event):
    ti = event.get("tool_input") or {}
    own = str(ti.get("file_path", ""))
    named = frozenset(p for p in _PATH_RX.findall(str(ti.get("content", ""))) if p != own)
    known = frozenset(p for p in named if any(_names(o, p) or p in str(o.output) for o in record.obs))
    return [tuple(sorted(known))] if known else []


def read_pays(args, cfg, o):
    if o.failed or not (o.tool == "Read" or (o.tool == "Bash" and str(o.output).strip())):
        return None
    return lambda paths: any(_names(o, p) for p in (paths if isinstance(paths, tuple) else (paths,)))


_LANDED = {
    "merged": re.compile(r"\bmerged\b", re.I),
    "landed": re.compile(r"\bmerged\b|\blanded\b|\b[0-9a-f]{7,40}\.\.[0-9a-f]{7,40}\b", re.I),
    "pushed": re.compile(r"\bpushed\b|\s->\s|Everything up-to-date", re.I),
    "passed": re.compile(r"\bpassed\b|\bPASS(?:ED)?\b", re.I),
    "passes": re.compile(r"\bpassed\b|\bPASS(?:ED)?\b", re.I),
    "shipped": re.compile(r"\bmerged\b|\bshipped\b|\breleased\b", re.I),
    "green": re.compile(r"\bpassed\b|\bsuccess\b|\bgreen\b", re.I),
}
_CLAIM_RX = re.compile(r"\b(merged|landed|pushed|passed|passes|shipped|green|completed?|ready)\b", re.I)
_NEG_RX = re.compile(r"\b(not|never|no|yet|once|until|if|when|before)\b|n't\b", re.I)
_PENDING_RX = re.compile(r"\b(queued|pending|running|started|launched)\b", re.I)


def _subject_words(text):
    # Identifier components also bind prose names to test nodes and job IDs.
    return set(re.findall(r"[a-z][a-z0-9]*|\d+", text.lower())) - _STOP_WORDS - {
        "all", "check", "checks", "test", "tests", "generation",
        "successfully", "consumers", "and", "ci", "has", "was", "rest", "their", "failed", "passed", "suite", "run",
        "now", "already", "still", "currently"}



# Number grammar reused from gate.unnamed_failure (6afe37e); prose counts,
# unlike runner summaries, can place a subject between number and verdict.
_FAILURE_UNIT = r"(?:one|two|three|four|five|six|seven|eight|nine)"
_FAILURE_COUNT = (rf"(?:[1-9]\d*|{_FAILURE_UNIT}|ten|eleven|twelve|(?:thir|four|fif|six|seven|eigh|nine)teen"
                  rf"|(?:twen|thir|for|fif|six|seven|eigh|nine)ty(?:[\s-]{_FAILURE_UNIT})?|(?:a\s+)?dozen|(?:a\s+)?hundred)")
_FAILURE_SUBJECT = r"(?:tests?|checks?|cases?|specs?|suites?|assertions?|examples?)"
_FAILURE_VERDICT = r"(?:fail(?:s|ed|ing)?|failures?|errors?|erroring|errored)"
_FAILURE_REPORT_RX = re.compile(
    rf"\b{_FAILURE_COUNT}\s+(?:[\w-]+\s+){{0,2}}{_FAILURE_SUBJECT}\s+(?:[\w-]+\s+){{0,2}}{_FAILURE_VERDICT}\b"
    rf"|\b{_FAILURE_COUNT}\s+{_FAILURE_VERDICT}(?:\s+{_FAILURE_SUBJECT})?\b"
    rf"|\b(?:{_FAILURE_SUBJECT}\s+)?(?:failures?|errors?|failed)\s*:\s*[1-9]\d*\b", re.I)
_TEST_OUTCOME_RX = re.compile(
    r"^\s*(FAILED|PASSED)\s+([\w./-]+::[\w:.-]+(?:\[[^\]\n]+\])?)"
    r"|^\s*(FAIL|ERROR):\s+(test_\w+)\s+\(([^)]+)\)"
    r"|^\s*(test_\w+)\s+\(([^)]+)\)\s+\.\.\.\s+(ok|FAIL|ERROR)\b", re.M)


def _failed_test_subjects(record):
    # Reuse the observed shell tokenizer: displaying a log is not running tests.
    verdicts = {}
    for o in record.obs:
        if o.tool != "Bash" or o.failed:
            continue
        runners = [argv for argv, _ in _R._segments(str(o.input.get("command", "")))
                   if argv and (os.path.basename(argv[0]) in ("pytest", "py.test") or
                       (re.fullmatch(r"python[0-9.]*", os.path.basename(argv[0])) and
                        tuple(argv[1:3]) in (("-m", "pytest"), ("-m", "unittest"))))]
        if not runners:
            continue
        for m in _TEST_OUTCOME_RX.finditer(o.output):
            status, node, unit_status, unit_name, unit_class, verbose_name, verbose_class, verbose_status = m.groups()
            identity = node or (unit_class + "::" + unit_name if unit_name else verbose_class + "::" + verbose_name)
            verdicts[identity] = (status or unit_status or verbose_status) not in ("PASSED", "ok")
    return [node for node, failed in verdicts.items() if failed]


def _unnamed_failures(record, event, cfg):
    text = _text_of(event)
    reports = []
    for sentence in _sentences(_strip_quoted(text)):
        if sentence.rstrip().endswith("?") or _SOURCE_NAMED_RX.search(sentence):
            continue
        for m in _FAILURE_REPORT_RX.finditer(sentence):
            if not _NEG_RX.search(sentence[:m.start()][-cfg["negation_window"]:]):
                reports.append(m)
    if not reports:
        return []
    # Inline code can NAME a failure even though quoted counts are not assertions.
    tokens = {token.rstrip(".:/-") for token in re.findall(r"[\w./:-]+(?:\[[^\]\n]+\])?", text)}
    missing = [node for node in _failed_test_subjects(record)
               if not tokens.intersection({node, node.rsplit("::", 1)[-1].split("[", 1)[0],
                   os.path.splitext(os.path.basename(node.split("::", 1)[0]))[0]})]
    return [("failed", frozenset(missing), "failure-report", -1)] if missing else []


def landed_owes(args, cfg, record, event):
    out = _unnamed_failures(record, event, cfg)
    if cfg.get("dispatch"):
        claims = [s for s in _sentences(_strip_quoted(_text_of(event)))
                  if not s.rstrip().endswith("?") and not _SOURCE_NAMED_RX.search(s)
                  and not _NEG_RX.search(s) and not _PENDING_RX.search(s)
                  and re.search(r"\b(done|fixed|finished|completed?)\b", s, re.I)]
        if claims:
            out.extend(("done", command, "acceptance", seq)
                       for seq, brief in getattr(record, "dispatch_briefs", ())
                       for command in _brief_fields(brief)["ACCEPTANCE"])

    for s in _sentences(_strip_quoted(_text_of(event))):
        if s.rstrip().endswith("?") or _SOURCE_NAMED_RX.search(s):
            continue
        for m in _CLAIM_RX.finditer(s):
            if _NEG_RX.search(s[:m.start()][-cfg["negation_window"]:]):
                continue
            word = m.group(1).lower()
            names = _subject_words(re.split(r"\band\b|;", s[:m.start()], flags=re.I)[-1])
            artifacts = {p for o in record.obs for p in (o.written | o.created |
                         set(re.findall(r"(?:--output(?:=|\s+)|-o\s+)([^\s;]+)",
                                        str(o.input.get("command", "")))))
                         if _subject_words(os.path.splitext(os.path.basename(p))[0]) <= names
                         and _subject_words(os.path.splitext(os.path.basename(p))[0])}
            # An artifact commits to its bytes, not a generator's exit or existence.
            if word in ("complete", "completed", "ready"):
                jobs = any(names & _subject_words(str(o.input.get("job_id", "")) +
                           " ".join(re.findall(r"\bjob_id[=:]([\w-]+)", o.output)))
                           for o in record.obs)
                if not artifacts and not jobs:
                    continue
            else:
                artifacts = set()
            if artifacts:
                out.extend((word, p, "artifact", max((o.seq for o in record.obs
                           if _names(o, p)), default=-1))
                           for p in sorted(artifacts))
            else:
                # Keep the claimed subject, including numeric identifiers. An unrelated
                # status must not erase its name and turn it into an aggregate claim.
                names = frozenset(names)
                failed_at = max((o.seq for o in record.obs if any(
                    names <= _subject_words(line + json.dumps(o.input)) and re.search(r"\b(fail(?:ed)?|error|queued|pending|running)\b", line, re.I)
                    for line in o.output.splitlines())), default=-1)
                out.append((word, names, "status", failed_at))
    return out


def _valid_artifact(o, path):
    if o.tool not in ("Read", "Write") or not _names(o, path):
        return False
    body = str(o.input.get("content", "") if o.tool == "Write" else o.output).strip()
    if not body:
        return False
    try:
        if path.lower().endswith(".json"):
            return bool(json.loads(body))
        if path.lower().endswith(".xml"):
            root = ET.fromstring(body)
            return bool(len(root) or (root.text or "").strip())
    except (ValueError, ET.ParseError):
        return False
    return True


def landed_pays(args, cfg, o):
    if not _primary(o):
        return None

    def pays(subject):
        word, names, kind, after = subject
        if kind == "failure-report":
            return False
        if kind == "acceptance":
            return (o.seq > after and o.tool == "Bash" and o.exit == 0
                    and o.input.get("command", "").strip() == names
                    and not o.input.get("run_in_background")
                    and o.seq not in cfg.get("dispatch_background", ())
                    and not _PENDING_RX.search(o.output))
        if not (o.output.strip() or (o.tool == "Write" and o.input.get("content"))):
            return False
        if o.seq < after:
            return False
        if kind == "artifact":
            return o.exit in (None, 0) and _valid_artifact(o, names)
        if o.seq <= after or o.input.get("run_in_background") or o.tool.endswith("__launch") or _PENDING_RX.search(o.output):
            return False
        rx = _LANDED.get(word, re.compile(r"\b(completed?|ready)\b", re.I))
        # JSON status fields and individual text lines keep named outcomes separate
        # from summaries. Input identifiers bind status APIs, never launch acknowledgements.
        for line in o.output.splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                value = None
            if isinstance(value, dict):
                if any((not names or names <= _subject_words(str(k)) or
                        (k in ("status", "state") and names <= _subject_words(json.dumps(o.input))))
                       and rx.search(str(v)) and not _NEG_RX.search(str(v))
                       for k, v in value.items()):
                    return True
                continue
            if re.search(r"\b(fail(?:ed)?|error)\b", line, re.I):
                continue
            if rx.search(line) and not _NEG_RX.search(line[:rx.search(line).start()]) and (not names or names <= _subject_words(line)
                                   or names <= _subject_words(json.dumps({k: v for k, v in o.input.items()
                                       if k != "command" or word in ("merged", "landed", "pushed", "shipped")}))):
                return True
        return False
    return pays



def count_owes(args, cfg, record, event):
    rx = re.compile(
        r"(?<![\w.])(\d+)\s+(?:[A-Za-z\-]+\s+){0,%d}?(?:in|of|from|at|under|across)\s+`?"
        r"((?:~|\.{1,2})?/?(?:[\w.\-]+/)*[\w.\-]+\.[A-Za-z0-9]+|/?(?:[\w.\-]+/)+[\w.\-]*)`?" % cfg["count_word_gap"])
    return [m.group(2).rstrip(".,;:") for m in rx.finditer(_text_of(event))]


def repeat_owes(args, cfg, record, event):
    if event.get("tool_name") != "Bash":
        return []
    command = (event.get("tool_input") or {}).get("command")
    last = next((o for o in reversed(record.obs) if o.tool == "Bash"
                 and o.input.get("command") == command), None)
    if last is None or last.exit is None:
        return []
    if last.exit == 0 and ">>" not in str(command):
        return []
    return [last.seq]


def wrote_pays(args, cfg, o):
    return (lambda seq: o.seq > seq) if o.tool in ("Write", "Edit") else None


PREDICATES = {
    "dispatch_schema": Spec(dispatch_schema_owes, why="dispatch fields required by I1"),
    "absence_unsearched": Spec(absence_owes, absence_pays,
                               why="claims absence with no empty search whose scope covers it"),
    "relayed_number": Spec(number_owes, number_pays,
                           why="a number no primary observation carries and no source is named for"),
    "user_quote": Spec(quote_owes, quote_pays, quote_seed,
                       why="quotes the user with words no observed user message or WORDS.tsv holds"),
    "write_unread_paths": Spec(write_owes, read_pays, why="writes about paths none of which was read"),
    "landed_unobserved": Spec(landed_owes, landed_pays,
                              why="claims an outcome without its observed status or counted failing subjects"),
    "count_unread_path": Spec(count_owes, read_pays, why="gives a count for a path never read"),
    "exact_repeat": Spec(repeat_owes, wrote_pays, why="replays an append or retries a failed command without an intervening edit"),
}
