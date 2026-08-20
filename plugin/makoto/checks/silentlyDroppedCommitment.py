from __future__ import annotations
import os
import re
from typing import Optional
from makoto.checks import normalize_path
from makoto.vocab import _EMPTY_OK, _FENCE_SPAN_RX
from makoto.vocab import Finding
from makoto.kit import _path_components, _suffix_match


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
_DROP_DET = r"(?:a\s+|an\s+|the\s+|new\s+)*"
def _drop_loc_tail(preps):
    """The OPTIONAL trailing '<preposition> <path>' locator the claim regexes share — same body
    (clause-bounded, non-greedy, capturing `loc`), only the preposition set differs per kind."""
    return rf"(?:\b[^.;\n]*?\b(?:{preps})\s+(?P<loc>{_DROP_PATH}))?"
_DROP_RX_COUNT = re.compile(
    rf"{_DROP_PRE}\s+(?:a\s+|an\s+|the\s+)?(\d+)\s+(?:new\s+|more\s+|additional\s+)?({_DROP_THING})"
    + _drop_loc_tail("to|in|into|inside|for|under|within"), re.I)
_DROP_RX_LINES = re.compile(
    rf"{_DROP_PRE}\s+(?:lines?\s+)(\d+)\s*(?:-|–|to|through|thru)\s*(\d+)"
    + _drop_loc_tail("of|in|to|into|within"), re.I)
_DROP_RX_SYMBOL = re.compile(
    rf"{_DROP_PRE}\s+{_DROP_DET}{_DROP_SYMDEF}"
    + _drop_loc_tail("to|in|into|inside|within"), re.I)
_DROP_RX_ARTIFACT = re.compile(
    rf"{_DROP_PRE}\s+{_DROP_DET}(?:file\s+|module\s+|script\s+|config\s+)?(?P<loc>{_DROP_PATH})", re.I)
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
def _drop_extract_forward_claims(text):
    """[(kind, location, info, raw)] — a forward mutation frame + EXACTLY ONE identifying
    info + a resolvable-looking location. Vague promises (no info / no path) -> []. Precedence
    most-specific first (line_range > count > named_symbol > named_artifact); a span is
    consumed by the first match. Negated forward frames are dropped. A frame inside a
    ```code fence``` is QUOTED text (a shell command, a demo, someone else's words), never the
    assistant's own commitment -- the L0 single-source `vocab._FENCE_SPAN_RX` decides what a
    fence is, the same object `substrate/claims.py` and `state/commitments.py` consume; before
    this exclusion a count claim pasted verbatim inside a fence fired a BLOCK the turn could
    not discharge, because nothing was promised."""
    if not text:
        return []
    claims, consumed = [], []
    fenced = [m.span() for m in _FENCE_SPAN_RX.finditer(text)]

    def _overlaps(a, b):
        return any(not (b <= s or a >= e) for s, e in consumed)

    def _fenced_start(a):
        return any(s <= a < e for s, e in fenced)

    def _negated(m):
        pre = text[max(0, m.start() - 24):m.start()]
        return bool(_DROP_NEG_FRAME_RX.search(pre) or _DROP_NEG_FRAME_RX.search(m.group(0)[:40]))

    def _candidates(rx, *, require_loc=False):
        """Live (unconsumed, unnegated) matches of `rx`. Lazy on purpose: `consumed` keeps
        growing as the caller appends the spans it actually turns into claims, so a match the
        caller SKIPS (n<=0, unlocatable artifact) leaves its span free for a later kind."""
        for m in rx.finditer(text):
            if _overlaps(m.start(), m.end()) or _negated(m) or _fenced_start(m.start()):
                continue
            if require_loc and not m.group("loc"):
                continue
            yield m

    for m in _candidates(_DROP_RX_LINES, require_loc=True):
        lo, hi = int(m.group(1)), int(m.group(2))
        if hi < lo:
            lo, hi = hi, lo
        claims.append(("line_range", m.group("loc"), (lo, hi), m.group(0)))
        consumed.append((m.start(), m.end()))
    for m in _candidates(_DROP_RX_COUNT, require_loc=True):
        n = int(m.group(1))
        if n <= 0:
            continue
        claims.append(("count", m.group("loc"), n, m.group(0)))
        consumed.append((m.start(), m.end()))
    # require_loc, exactly like count/line_range above: a symbol claim with no trailing path
    # is a vague promise per this function's own contract ("no info / no path -> []"). The old
    # `m.group("loc") or sym` fallback used the SYMBOL NAME as the location, which never
    # resolves and never reads, so the discharge test returned False unconditionally -- a BLOCK
    # on a false fact ("claimed to define `parse_config` in parse_config") even when the def
    # was sitting in a touched file, with a non-path in the Finding's file field.
    for m in _candidates(_DROP_RX_SYMBOL, require_loc=True):
        sym = m.group(1)
        claims.append(("named_symbol", m.group("loc"), sym, m.group(0)))
        consumed.append((m.start(), m.end()))
    for m in _candidates(_DROP_RX_ARTIFACT):
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
    touch or a non-empty file.

    Follows completion_gate's content-deep discharge, with a DELIBERATE and bounded difference,
    stated here because the docstring used to claim it "mirrors" the ledger's `_discharged` and
    does not: `_discharged` applies the `_EMPTY_OK` conventional-empty carve-out globally, while
    this applies `conventional` on the `named_artifact` and `line_range` branches only.
    `named_symbol` and `count` ask a question emptiness cannot answer -- a claim to add 2 exports
    to `pkg/__init__.py` is not discharged by that file being empty, however conventional its
    emptiness is in general. So on a zero-byte conventional file with a count/symbol claim,
    `gate.completion` discharges and `gate.dropped` fires, on identical ledger state. That is the
    intended reading of two different questions, not an oversight -- but it IS a divergence, and
    an unstated divergence behind a claim of mirroring is how the next reader "fixes" one of them
    into agreement and silently deletes a gate."""
    content = fs_read(path) if (fs_read is not None and path) else None
    touched = _drop_touched(path, touched_keys, empty_keys)
    exists = bool(fs_exists and path and fs_exists(path))
    size = fs_size(path) if (fs_size and path) else None
    # Conventional empties (__init__.py etc.): emptiness IS the deliverable — mirrors
    # _shared._discharged's _EMPTY_OK rule (consolidation T2.4; fired on honest empties before).
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
        if content is None:
            return False
        return bool(re.search(
            rf"^\s*(?:async\s+def|def|class|const|function\*?)\s+{re.escape(info)}\b",
            content, re.M))
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


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.dropped", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="CLAIM_VS_LEDGER",
               eats=frozenset({"text", "touched", "fs_exists", "fs_size", "fs_read", "empty"}),
               run=lambda c: dropped_gate(c.text, touched_keys=c.touched, fs_exists=c.fs_exists, fs_size=c.fs_size, fs_read=c.fs_read, empty_keys=c.empty))
