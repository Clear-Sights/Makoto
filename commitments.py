"""Commitments store: source open located commitments from REAL payload fields and
persist / read them un-windowed by session.

A commitment is a forward promise the AI made that names a location (+ optional
quantity). The advance gate later checks whether the AI moved PAST it without
discharging it. Sourcing is deterministic — detect_location (+ detect_quantity) over
the real text the assistant emitted (last_assistant_message), a Task tool's prompt,
or a plan-edit — never an assumed-present TodoWrite (this environment emits none).

Open commitments are read UN-WINDOWED (by session, not via the 1-hour event slice):
a promise doesn't expire because an hour passed. commitment_key = sha1(session +
normalized location + span) so re-stating the same promise doesn't duplicate.

Stdlib only; no LLM, no HTTP.
Spec: docs/archive/specs/2026-05-31-makoto-bidirectional-falsifiability-design.md §5 (gates), §8 (stores).
"""
from __future__ import annotations
import hashlib
import re
from typing import Optional

from makoto.checks import detect_locations, detect_quantity, normalize_path
from makoto.lexicons import _BE_AUX_RX  # L0 shared lexicon (dedup: was a byte-identical local copy)

# A commitment is a FORWARD promise to produce/modify a named file: a PRODUCE VERB (add/
# implement/build/create/write/wire/fix/introduce) that GOVERNS the path as its object/
# destination — "add rate-limit to src/auth.py", "I'll write `docs/x.md`". Mirrors
# gates._production_claim_location's clause discipline (verb BEFORE the path, SAME clause,
# active voice) but accepts the forward framing (a promise, not a completion). A PAST claim
# ("added/wrote X") is a completion the completion gate owns. The governing requirement is the
# advance gate's FP fix, distilled from a real-session corpus: a bare promise-keyword anywhere
# near a path over-sources phantom commitments off a MENTION — a path in an ASCII tree
# ("└── stop.sh", where "write" leaks from "read/write ratio"), a noun-modifier ("settings.json
# keys", "CLAUDE.md convention" — no produce verb governs them), a read verb ("agents are
# reading X"), or a conditional offer ("if you greenlight, I can write X"). Requiring the
# produce verb to govern the path keeps the commitment verifiable, never a guess.
# Word-boundary inflections only — NOT a greedy \w* that would swallow an identifier
# ("build_live_scorer", "writer", "fixture") and misread it as the verb.
_PRODUCE_VERB_RX = re.compile(
    r"\b(?:add(?:s|ing)?|implement(?:s|ing)?|build(?:s|ing)?|creat(?:e|es|ing)|"
    r"writ(?:e|es|ing)|wir(?:e|es|ing)|fix(?:es|ing)?|introduc(?:e|es|ing))\b",
    re.IGNORECASE)
_PAST_PRODUCE_RX = re.compile(
    r"\b(added|implemented|built|created|wrote|written|wired|fixed|done|finished|"
    r"completed|saved|updated|landed|committed)\b", re.IGNORECASE)
# A NEGATED promise ("I will not add X", "won't implement X", "not going to add X") is NOT a
# commitment — it is a retraction (retraction.surfaced_retraction_locations owns it). Recording it
# would create a phantom open commitment the advance gate then false-fires on.
_NEGATED_PROMISE_RX = re.compile(
    r"\b(?:do not|don'?t|won'?t|will not|will never|never|not going to|never going to|"
    r"not planning to|no longer)\s+"
    r"(?:add|implement|build|create|writ|includ|wire|introduc|need|do|plan)\w*",
    re.IGNORECASE)
# A clause boundary OR a tree/diagram glyph OR a pipe between the verb and the path -> the verb
# governs a different clause, or a different cell of a file-listing, not this path.
_GOVERN_BREAK_RX = re.compile(r"[.;:\n—|│]|──|[├└┌┐┘]")
# A conditional/hypothetical OFFER governing the promise -> not a firm commitment.
_OFFER_COND_RX = re.compile(r"\b(?:if|once|unless|assuming|provided|whether|in case)\b",
                            re.IGNORECASE)
# Makoto watches the AI's OWN promises: a commitment needs a FIRST-PERSON subject ("I'll add X",
# "we need to write X") OR a clause-initial imperative ("Add X to Y"). A THIRD-PERSON or
# adverbial subject — "the fold fork writing X" (a subagent's action), "before adding entries to
# X" (an adverbial gerund), "it leans on a CLAUDE.md convention" — is NOT a promise the AI made.
_FIRST_PERSON_RX = re.compile(
    r"\b(?:i|we|i'?ll|we'?ll|i'?m|we'?re|i'?ve|we'?ve|i'?d|we'?d|let'?s|my|our)\b", re.IGNORECASE)
# A box-drawing/tree glyph on the path's line -> a file-listing, not prose. Never a promise.
_TREE_GLYPH_RX = re.compile(r"[│├└┌┐┘┤┬┴┼─╾╿]")
# The verb is line-initial (optionally after a bullet/number) -> an imperative plan-item
# ("Add X to Y"). A verb mid-line after other words is NOT imperative; it needs a first-person
# subject to count as the AI's own promise.
_LINE_INITIAL_RX = re.compile(r"^[\s\-*•>\d.)\]]*$")
# An OPTIONALITY marker inside a parenthetical ATTACHED to the path ("Add X (opt-in)", "create Y
# (optional)") marks the path itself as an optional / proposed feature offered for approval — not a
# firm promise. Voids the commitment so the advance gate never fires on an un-greenlit option. The
# distilled corpus FP (session d2595e7a): `Add cache_semantic.py (… opt-in via pip install …[heavy])`.
# Scoped to a parenthetical ON the path (0-FN): "add an opt-in flag to config.py" has no parenthetical
# and still sources, because there "opt-in" modifies the flag, not the file.
_OPTIONAL_MARK_RX = re.compile(r"\b(?:opt-?in|optional|nice[- ]to[- ]have)\b", re.IGNORECASE)
# A parenthetical right after the path: allow a trailing closing backtick / quote / space first.
_PATH_PAREN_RX = re.compile(r"[\s`'\"]*\(([^)]*)\)")
# A path introduced under a PROPOSAL section header — "**N. New Task 15.5 — paid lookup tiebreak**",
# "heavy-opt-in cache layer" — is a proposed task in a plan the AI is PRESENTING FOR APPROVAL, not a
# firm promise. The distilled advance-gate corpus FP (session d2595e7a): a plan-audit turn lists
# "Add X" bullets under "New Task N.M" / "## What's worth building" / "Option A:" headers, then
# later claims done about OTHER work. Proven 0-FN against the replay: EVERY genuine commitment in
# session d2595e7a discharged (its file was touched), so excluding proposal framing cannot drop a
# real promise — a truly broken promise ("I'll build X", never built) does not use proposal idioms.
# STRONG idioms only: "I'll add flags.py to make the cache optional" (a real promise) must NOT match.
# Noun-phrase / structural proposal idioms ONLY — a verb-clause marker ("could add", "should
# build") would over-match "it could add value, so I'll build X" and drop a real promise; these
# noun forms never govern a genuine first-person commitment.
_PROPOSAL_MARK_RX = re.compile(
    r"\bnew task\s+\d|\bheavy[- ]opt-?in|\bworth building\b|\bconcrete additions?\b|"
    r"\bproposed\s+(?:additions?|tasks?|changes?|files?)\b|\boption\s+[A-Z]\b",
    re.IGNORECASE)
# A path INSIDE a fenced code block (```...```) is code — a shell command, a config snippet, a
# `git reset --hard` demo (`echo "..." > critical_notes.txt`) — displayed, not promised. Same
# family as the file-tree / table-row guard: a real promise is FIRST-PERSON ENGLISH PROSE, never a
# line in a code fence. The 3rd reproduced advance-gate corpus FP (session d2595e7a): a demo's
# redirect target sourced because the demo string "MY UNSAVED CRITICAL WORK" trips first-person.
# Fence parity: an ODD count of ``` fences before the path's offset means the path sits inside one.
_FENCE_RX = re.compile(r"(?m)^\s{0,3}```")
_BIND_BEFORE = 70


def _non_prose_line(line: str) -> bool:
    """A file-tree diagram (box glyphs) or a markdown TABLE row (>=2 cell pipes) — a listing,
    not a sentence. A path here is displayed, not promised."""
    return bool(_TREE_GLYPH_RX.search(line)) or line.count("|") >= 2


# Dotless filename conventions that ARE real files when capitalized as such.
_KNOWN_DOTLESS = {"makefile", "dockerfile", "license", "readme", "copying", "changelog",
                  "notice", "procfile", "gemfile", "rakefile", "jenkinsfile", "vagrantfile",
                  "authors", "contributing", "codeowners"}


# A plausible file EXTENSION: short, LOWERCASE, alphanumeric, not purely numeric. This is the
# firewall that separates a filename ('x.py', 'README.md') from a dotted CODE IDENTIFIER
# ('Finding.source_event_id' — tail 'source_event_id' is long+underscored; 'Module.Class' — tail
# is capitalized; 'obj.method' — tail too long), a version/pattern id ('v1.2', '1.4' — tail is
# digits), or a dotted-attr chain ('schema.load_prechecks'). Real extensions are lowercase by
# convention, so requiring lowercase rejects 'Class'/'PY' identifier tails 0-FN on real promises.
_FILE_EXT_RX = re.compile(r"[a-z0-9]{1,5}")
# A leading-slash word with no inner separator is a SLASH-COMMAND ('/loop', '/makoto:status'),
# not a filesystem path — detect_locations over-matched the leading '/'.
_SLASH_COMMAND_RX = re.compile(r"/[A-Za-z][\w:.-]*")


def _is_file_shaped(loc: str) -> bool:
    """A commitment to PRODUCE a file must name a file-shaped token: a path separator, a dotted
    name whose LAST segment is a plausible file extension, OR a known dotless convention spelled
    with a capital (LICENSE, Makefile). A bare lowercase word ("main", "data"), a dotted CODE
    IDENTIFIER ("Finding.source_event_id", "Module.Class", "obj.method" — the tail is not a real
    extension), a version/pattern id ("v1.2", "1.4"), or a slash-command ("/loop") is prose/code
    that detect_locations over-matched — never the object of a real file promise (the live
    advance-gate FP this guard closes: a class attribute persisted as a phantom open commitment)."""
    if _SLASH_COMMAND_RX.fullmatch(loc):
        return False                              # '/loop', '/makoto:status' -> a command token
    if "/" in loc or "\\" in loc:
        return True
    core = loc.strip(".")
    if "." in core:
        ext = core.rsplit(".", 1)[1]
        return bool(_FILE_EXT_RX.fullmatch(ext)) and not ext.isdigit()  # plausible ext, not a code/id tail
    return bool(re.search(r"[A-Z]", loc)) and loc.lower() in _KNOWN_DOTLESS


def _promise_location(text: str) -> Optional[str]:
    """First path that is the object/destination of an ACTIVE, FIRST-PERSON forward production
    promise, else None. A produce verb must GOVERN the path (verb before path, same clause,
    active) AND the verb's clause must be first-person or imperative. A past claim, a negated
    promise, a passive/copular frame, a conditional offer, a third-person/adverbial subject, a
    file-tree listing, or a path no produce verb governs (a mention, a noun-modifier) stay
    inert — that is what keeps the advance gate from false-firing on a non-commitment."""
    for loc, a, b in detect_locations(text):
        if not _is_file_shaped(loc):
            continue                              # bare lowercase word -> prose, not a real file
        ls = text.rfind("\n", 0, a) + 1
        le = text.find("\n", b)
        if _non_prose_line(text[ls:le if le != -1 else len(text)]):
            continue                              # path sits in a file-tree diagram or table row
        if len(_FENCE_RX.findall(text[:a])) % 2 == 1:
            continue                              # path sits inside a ```fenced code block``` -> code, not a promise
        if _PROPOSAL_MARK_RX.search(text[max(0, ls - 200):a]):
            continue                              # path sits under/within a proposal header ("Option A:", "New Task N", "worth building")
        before = text[max(0, a - _BIND_BEFORE):a]
        if _PAST_PRODUCE_RX.search(before):
            continue                              # "added X" -> completion, not a promise
        if _NEGATED_PROMISE_RX.search(before + " " + text[b:b + 8]):
            continue                              # "won't add X" -> retraction, not a promise
        mp = _PATH_PAREN_RX.match(text[b:])
        if mp and _OPTIONAL_MARK_RX.search(mp.group(1)):
            continue                              # "Add X (opt-in/optional)" -> an offered option, not a promise
        for vm in _PRODUCE_VERB_RX.finditer(before):
            if _GOVERN_BREAK_RX.search(before[vm.end():]):
                continue                          # verb governs a different clause / diagram cell
            pre = before[:vm.start()]
            if _BE_AUX_RX.search(pre):
                continue                          # "X is wired" -> a state, not a promise
            if _OFFER_COND_RX.search(pre[-46:]):
                continue                          # "if you greenlight ... write X" -> an offer
            line_pref = text[ls:max(0, a - _BIND_BEFORE) + vm.start()]
            if not _LINE_INITIAL_RX.match(line_pref) and not _FIRST_PERSON_RX.search(line_pref):
                continue                          # mid-line, no first-person subject -> not my promise
            return loc                            # a first-person/imperative produce verb governs path
    return None


def source_commitment(text: str) -> Optional[dict]:
    """Parse a forward commitment from `text`.

    Returns {location, qty_min, qty_max} for the first named file path that is the OBJECT of a
    forward production promise (a produce verb governing it, active, non-past, non-negated, non-
    conditional), else None (inert). Being inert on a path that is merely mentioned — listed in
    a tree, used as a noun-modifier, read, or offered conditionally — is what keeps the advance
    gate from false-firing on a commitment the AI never actually made.
    """
    if not text:
        return None
    loc = _promise_location(text)
    if not loc:
        return None
    qty = detect_quantity(text)
    qmin, qmax = qty if qty else (None, None)
    return {"location": normalize_path(loc), "qty_min": qmin, "qty_max": qmax}


def commitment_key(session_id: str, location: str, qmin, qmax) -> str:
    raw = f"{session_id}\x00{normalize_path(location)}\x00{qmin}\x00{qmax}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def record_commitment(conn, session_id: str, commitment: dict, *, created_event_id) -> str:
    """Persist an OPEN commitment (idempotent on commitment_key). Returns the key."""
    key = commitment_key(session_id, commitment["location"],
                         commitment["qty_min"], commitment["qty_max"])
    # On re-promise of an identical commitment: leave 'open'/'discharged' untouched, but
    # RE-OPEN a 'retracted' one — the AI un-dropped it ("actually I will add X after all").
    # The commitment_key is deterministic, so without this a re-promise is silently swallowed.
    conn.execute(
        "INSERT INTO commitments (commitment_key, session_id, location, qty_min, qty_max, "
        "status, created_event_id) VALUES (?, ?, ?, ?, ?, 'open', ?) "
        "ON CONFLICT(commitment_key) DO UPDATE SET status = 'open' "
        "WHERE commitments.status = 'retracted'",
        [key, session_id, commitment["location"], commitment["qty_min"],
         commitment["qty_max"], created_event_id])
    conn.commit()
    return key


def open_commitments(conn, session_id: str) -> list[dict]:
    """Read OPEN commitments for a session, UN-WINDOWED (not via the 1-hour slice)."""
    rows = conn.execute(
        "SELECT commitment_key, location, qty_min, qty_max FROM commitments "
        "WHERE session_id = ? AND status = 'open'", [session_id]).fetchall()
    return [{"commitment_key": r[0], "location": r[1], "qty_min": r[2], "qty_max": r[3]}
            for r in rows]


def set_status(conn, key: str, status: str, *, retract_param: Optional[str] = None) -> None:
    """Transition a commitment to discharged | retracted (with the retract parameter)."""
    conn.execute(
        "UPDATE commitments SET status = ?, retract_param = ? WHERE commitment_key = ?",
        [status, retract_param, key])
    conn.commit()


def retire_unsourceable_commitments(
        conn, session_id: str, *,
        reason: str = "stale mis-source: location not file-shaped under current sourcing rules"
) -> list[dict]:
    """Sanctioned GC of stale PHANTOM commitments. Retire OPEN commitments whose location is NOT
    file-shaped under the CURRENT `_is_file_shaped` rules — rows the live sourcer would never
    create (a pre-hardening mis-source: a dotted code identifier like 'Finding.source_event_id',
    a branch name 'main', a function 'detect_location', a slash-command '/loop').

    FN-SAFE BY CONSTRUCTION: a genuine file-shaped commitment (a real promised file, dischargeable
    normally) is NEVER touched — this can only clear provable non-obligations, never a real open
    promise. Auditable: the rationale is recorded in `retract_param`. Returns the retired rows
    [{location, commitment_key}]. NOT a self-bypass: it cannot clear a commitment whose location
    the current rules WOULD accept as a producible file."""
    retired = []
    for c in open_commitments(conn, session_id):
        if not _is_file_shaped(c["location"]):
            set_status(conn, c["commitment_key"], "retracted", retract_param=reason)
            retired.append({"location": c["location"], "commitment_key": c["commitment_key"]})
    return retired
