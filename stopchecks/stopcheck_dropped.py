from __future__ import annotations
import os
import re
from typing import Optional
from makoto.checks import normalize_path
from makoto.lexicons import _EMPTY_OK
from makoto.schema import Finding
from makoto.stopchecks._common import _path_components, _suffix_match
from makoto.stopchecks._types import StopCheck


_DROP_FORWARD = r"(?:I['’]?ll|I\s+will|I['’]?m\s+going\s+to|I\s+am\s+going\s+to|let\s+me|let['’]s|let\s+us|going\s+to|i\s+plan\s+to|next\s+i\s+will|we['’]?ll|we\s+will|i\s+need\s+to|i\s+should|i\s+want\s+to)"
_DROP_VERB = r"(?:add|create|write|implement|define|introduce|build|make|set\s+up|generate|edit|modify|update|change|patch|insert|append|launch)"
_DROP_THING = r"(?:helper\s+functions?|functions?|helpers?|tests?|methods?|classes|class|fields?|fixtures?|cases?|test\s+cases?|assertions?|validators?|checks?|handlers?|endpoints?|routes?|columns?|keys?|entries|examples?|imports?|sentinels?)"
_DROP_EXT = r"\.[A-Za-z][A-Za-z0-9]{0,7}"
_DROP_BASENAME = rf"[\w-]+{_DROP_EXT}"
_DROP_PATH = rf"(?:(?:[\w.~-]+/)*{_DROP_BASENAME})"
_DROP_NEG_FRAME_RX = re.compile(
    r"\b(?:never|won['’]?t|will\s+not|do\s+not|don['’]?t|didn['’]?t|wouldn['’]?t|"
    r"rather\s+than|instead\s+of|avoid|without|no\s+need\s+to|not\s+going\s+to)\b", re.I)
_DROP_SYMDEF = r"(?:async\s+def|def|class|const|function)\s+([A-Za-z_]\w*)"
_DROP_PRE = rf"{_DROP_FORWARD}\s+(?:\w+\s+){{0,2}}?{_DROP_VERB}\b"
_DROP_RX_COUNT = re.compile(
    rf"{_DROP_PRE}\s+(?:a\s+|an\s+|the\s+)?(\d+)\s+(?:new\s+|more\s+|additional\s+)?({_DROP_THING})"
    rf"(?:\b[^.;\n]*?\b(?:to|in|into|inside|for|under|within)\s+(?P<loc>{_DROP_PATH}))?", re.I)
_DROP_RX_LINES = re.compile(
    rf"{_DROP_PRE}\s+(?:lines?\s+)(\d+)\s*(?:-|–|to|through|thru)\s*(\d+)"
    rf"(?:\b[^.;\n]*?\b(?:of|in|to|into|within)\s+(?P<loc>{_DROP_PATH}))?", re.I)
_DROP_RX_SYMBOL = re.compile(
    rf"{_DROP_PRE}\s+(?:a\s+|an\s+|the\s+|new\s+)*{_DROP_SYMDEF}"
    rf"(?:\b[^.;\n]*?\b(?:to|in|into|inside|within)\s+(?P<loc>{_DROP_PATH}))?", re.I)
_DROP_RX_ARTIFACT = re.compile(
    rf"{_DROP_PRE}\s+(?:a\s+|an\s+|the\s+|new\s+)*(?:file\s+|module\s+|script\s+|config\s+)?(?P<loc>{_DROP_PATH})", re.I)
# Counts a defined callable in ANY surface form, so a "create N functions/helpers" count-claim
# discharges against lambda/arrow/partial-bound helpers too (the measured FP: 3 lambda-assigned
# helpers left the def-only counter at 0 and false-fired). Forms: py `def`/`class`; JS
# `function name`; assignment-bound callables — JS `const/let/var name = function|(...)=>|x=>|partial`
# and py `name = lambda|partial|functools.partial`. A line with NO callable binding (plain data
# assignment `x = 1`) is not counted, so the real TP (claim N, file has 0 callables of any form)
# still fires.
_DROP_DEF_COUNTER = re.compile(
    r"^\s*(?:async\s+def|def|class)\s+\w+"
    r"|^\s*(?:export\s+)?function\*?\s+\w+"
    r"|^\s*(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?"
      r"(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>|partial\b)"
    r"|^\s*\w+\s*=\s*(?:lambda\b|partial\b|functools\.partial\b)",
    re.M)
_DROP_TEST_COUNTER = re.compile(r"^\s*(?:async\s+def|def)\s+test\w*", re.M)
def _drop_def_or_class(sym):
    return re.compile(rf"^\s*(?:async\s+def|def|class|const|function\*?)\s+{re.escape(sym)}\b", re.M)
def _drop_extract_forward_claims(text):
    """[(kind, location, info, raw)] — a forward mutation frame + EXACTLY ONE identifying
    info + a resolvable-looking location. Vague promises (no info / no path) -> []. Precedence
    most-specific first (line_range > count > named_symbol > named_artifact); a span is
    consumed by the first match. Negated forward frames are dropped."""
    if not text:
        return []
    claims, consumed = [], []

    def _overlaps(a, b):
        return any(not (b <= s or a >= e) for s, e in consumed)

    def _negated(m):
        pre = text[max(0, m.start() - 24):m.start()]
        return bool(_DROP_NEG_FRAME_RX.search(pre) or _DROP_NEG_FRAME_RX.search(m.group(0)[:40]))

    for m in _DROP_RX_LINES.finditer(text):
        if _overlaps(m.start(), m.end()) or _negated(m) or not m.group("loc"):
            continue
        lo, hi = int(m.group(1)), int(m.group(2))
        if hi < lo:
            lo, hi = hi, lo
        claims.append(("line_range", m.group("loc"), (lo, hi), m.group(0)))
        consumed.append((m.start(), m.end()))
    for m in _DROP_RX_COUNT.finditer(text):
        if _overlaps(m.start(), m.end()) or _negated(m) or not m.group("loc"):
            continue
        n = int(m.group(1))
        if n <= 0:
            continue
        claims.append(("count", m.group("loc"), n, m.group(0)))
        consumed.append((m.start(), m.end()))
    for m in _DROP_RX_SYMBOL.finditer(text):
        if _overlaps(m.start(), m.end()) or _negated(m):
            continue
        sym = m.group(1)
        claims.append(("named_symbol", m.group("loc") or sym, sym, m.group(0)))
        consumed.append((m.start(), m.end()))
    for m in _DROP_RX_ARTIFACT.finditer(text):
        if _overlaps(m.start(), m.end()) or _negated(m):
            continue
        loc = m.group("loc")
        if not loc or not re.search(r"[\w-]+\.[A-Za-z]", loc):
            continue
        claims.append(("named_artifact", loc, os.path.basename(loc.rstrip("/")), m.group(0)))
        consumed.append((m.start(), m.end()))
    return claims
def _drop_resolve_location(L, touched_keys):
    """Resolve surface L to a path via the agent's OWN ledger: component-suffix vs a touched
    key. NO os.walk — an unbounded tree walk per claim is a Stop-hot-path landmine, and
    resolving a claimed title against the whole filesystem invites cross-project FPs. Discharge
    against a pre-existing on-disk file still works via the caller's cwd-relative fs_exists/
    fs_read on the unresolved surface (path=loc); genuinely-dropped work (never touched, never
    on disk) correctly fails to resolve and fires. (The dead `roots` param — kept while the dark
    meaning_gate still walked — died with that gate, io-purge P5.)"""
    Lc = _path_components(L)
    for k in (touched_keys or ()):
        if _suffix_match(Lc, _path_components(k)):
            return normalize_path(k)
    return None
def _drop_touched(path, touched_keys, empty_keys) -> bool:
    """A recorded NON-empty touch (Edit/Write/MultiEdit) backs this location (suffix match)."""
    pc = _path_components(path)
    empties = {normalize_path(k) for k in (empty_keys or ())}
    for k in (touched_keys or ()):
        if _suffix_match(pc, _path_components(k)) and normalize_path(k) not in empties:
            return True
    return False
def _drop_discharged(kind, info, raw, path, *, touched_keys, empty_keys, fs_exists, fs_size, fs_read) -> bool:
    """At turn-end, is the forward claim satisfied on `path`? Content-deep where the kind
    needs it (symbol/count read the file via fs_read); artifact/line discharge on a non-empty
    touch or a non-empty file. Mirrors completion_gate's content-deep discharge."""
    content = fs_read(path) if (fs_read is not None and path) else None
    touched = _drop_touched(path, touched_keys, empty_keys)
    exists = bool(fs_exists and path and fs_exists(path))
    size = fs_size(path) if (fs_size and path) else None
    # Conventional empties (__init__.py etc.): emptiness IS the deliverable — mirrors
    # _common._discharged's _EMPTY_OK rule (consolidation T2.4; fired on honest empties before).
    conventional = os.path.basename(path or "") in _EMPTY_OK
    if kind == "named_artifact":
        if conventional and (exists or _drop_touched(path, touched_keys, None)):
            return True                                  # an empty Write of __init__.py is the work
        if content is not None:
            return len(content.strip()) > 0
        if exists:
            return size != 0
        return touched
    if kind == "named_symbol":
        return bool(_drop_def_or_class(info).search(content)) if content is not None else False
    if kind == "count":
        if content is None:
            return False
        counter = _DROP_TEST_COUNTER if "test" in (raw or "").lower() else _DROP_DEF_COUNTER
        found = len(counter.findall(content))
        if found == 0 and counter is _DROP_TEST_COUNTER:
            found = len(_DROP_DEF_COUNTER.findall(content))
        return found >= info
    if kind == "line_range":
        if touched:
            return True
        if content is not None:
            return len(content.strip()) > 0 or conventional
        return exists and (size != 0 or conventional)
    return True                                          # unknown kind -> fail open
def dropped_gate(text, *, touched_keys, fs_exists=None, fs_size=None,
                 fs_read=None, empty_keys=None) -> Optional[Finding]:
    """Fire iff a FORWARD claim carrying identifying info (a count / line-range / named symbol
    / named artifact governed by a future-tense mutation verb) is NOT discharged at turn-end —
    the file is absent, or the claimed count/symbol/range is not present. The forgetful gate:
    said-but-not-done, a claim ✗ the assistant's own end-of-turn ledger/filesystem. A vague
    promise with no identifying info never extracts (so never fires); a negated frame
    ("I won't add X") never fires; a discharged claim is silent (fail-open)."""
    if not text:
        return None
    for kind, loc, info, raw in _drop_extract_forward_claims(text):
        path = _drop_resolve_location(loc, touched_keys) or loc
        if _drop_discharged(kind, info, raw, path, touched_keys=touched_keys, empty_keys=empty_keys,
                            fs_exists=fs_exists, fs_size=fs_size, fs_read=fs_read):
            continue
        loc_n = normalize_path(path)
        if kind == "count":
            desc = f"claimed {info} {os.path.basename(loc)}"
        elif kind == "line_range":
            desc = f"claimed an edit to lines {info[0]}-{info[1]}"
        elif kind == "named_symbol":
            desc = f"claimed to define `{info}`"
        else:
            desc = f"claimed to create `{os.path.basename(loc)}`"
        return Finding(
            pattern_id="gate.dropped", file=loc_n, line=0, level="error",
            message=(f"A forward claim {desc} in {loc_n}, but at turn-end the location does not "
                     f"contain it — said-but-not-done."),
            retry_hint="Do the claimed edit/add/create at the cited location, or retract it with a checked reason.")
    return None


GATE = StopCheck(
    id="gate.dropped",
    fn=dropped_gate,
    run=lambda c: dropped_gate(c.text, touched_keys=c.touched, fs_exists=c.fs_exists, fs_size=c.fs_size, fs_read=c.fs_read, empty_keys=c.empty),
)
