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

from makoto.checks import detect_locations, detect_quantity, normalize_path, subject_binds
from makoto.vocab import (
    _BE_AUX_RX, _OFFER_COND_RX, _FIRST_PERSON_RX,  # L0 shared lexicon (dedup: were byte-identical local copies)
    _NEG_FRAME_RX, _FENCE_SPAN_RX,
    _RETRACT_VERB_RX, _RETRACT_NEGPROMISE_RX, _RETRACT_POST_RX, _RETRACT_REASON_RX,
    _RETRACT_CLAUSE_BREAK_RX, _WRONG_SUBJECT_RX, _ACCIDENTAL_RX, _RETRACT_KEPT_RX,
    _RETRACT_ADVERSATIVE_RX,
)

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
# The dot alternative is a SENTENCE-ending dot only (followed by whitespace/EOL, not preceded by
# a single-letter abbreviation segment): a dot inside a dotted TOKEN between the verb and the
# path -- a version ("v1.2"), an abbreviation ("e.g."), "Node.js", "3.5s" -- is not a clause
# boundary, and treating it as one voided governance so the promise was never recorded
# (reproduced: "I'll add caching for the v1.2 endpoint to src/api.py" -> None, same text with
# "v12" -> sourced).
_GOVERN_BREAK_RX = re.compile(r"[;:\n—|│]|(?<!\b[A-Za-z])\.(?!\S)|──|[├└┌┐┘]")
# _OFFER_COND_RX / _FIRST_PERSON_RX: L0 shared lexicon (makoto.vocab, imported above) --
# _OFFER_COND_RX carves out a conditional/hypothetical OFFER from being read as a firm
# commitment; _FIRST_PERSON_RX requires a first-person subject or clause-initial imperative. A
# THIRD-PERSON or adverbial subject — "the fold fork writing X" (a subagent's action), "before
# adding entries to X" (an adverbial gerund) — is NOT a promise the AI made. (Dedup: was a
# byte-identical local copy, mirrored again in state/plan.py.)
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
# COMPLETE SPANS (the L0 single-source vocab._FENCE_SPAN_RX, via _fenced_spans below), not fence
# PARITY: parity counting silently flipped on an UNCLOSED fence, or on a closing fence indented
# >=4 spaces (a fenced block inside a list item), and suppressed sourcing for the whole remainder
# of the message — a promise stated in plain prose after the fence was never recorded. A span
# that never closes is no span, so prose after it sources (fail-open toward recording), while a
# genuinely fenced path stays suppressed.
# The verb->path binding window. 70 chars was too small to CONTAIN the verb of a long-form
# promise ("I'll add a comprehensive rate-limiting middleware with retry and backoff to
# src/auth.py" — verb->path gap 68 chars, so the verb started outside the window and the
# identical promise with a shorter object phrase sourced). The clause-break guard
# (_GOVERN_BREAK_RX) is what bounds governance semantically; this window is only a scan cost
# cap, so it must be comfortably larger than a real single-clause object phrase.
_BIND_BEFORE = 160


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
# is capitalized; 'obj.method' — tail too long), a version/pattern id ('v1.2', 'content.integrity_suppression_flag' — tail is
# digits), or a dotted-attr chain ('schema.load_prechecks'). Real extensions are lowercase by
# convention, so requiring lowercase rejects 'Class'/'PY' identifier tails 0-FN on real promises.
_FILE_EXT_RX = re.compile(r"[a-z0-9]{1,5}")
# A leading-slash word with no inner separator is a SLASH-COMMAND ('/loop', '/makoto:status'),
# not a filesystem path — detect_locations over-matched the leading '/'.
_SLASH_COMMAND_RX = re.compile(r"/[A-Za-z][\w:.-]*")
# A capital anywhere in the token -> the LICENSE / Makefile spelling of a dotless convention.
_HAS_CAPITAL_RX = re.compile(r"[A-Z]")


def _is_file_shaped(loc: str) -> bool:
    """A commitment to PRODUCE a file must name a file-shaped token: a path separator, a dotted
    name whose LAST segment is a plausible file extension, OR a known dotless convention spelled
    with a capital (LICENSE, Makefile). A bare lowercase word ("main", "data"), a dotted CODE
    IDENTIFIER ("Finding.source_event_id", "Module.Class", "obj.method" — the tail is not a real
    extension), a version/pattern id ("v1.2", "content.integrity_suppression_flag"), or a slash-command ("/loop") is prose/code
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
    return bool(_HAS_CAPITAL_RX.search(loc)) and loc.lower() in _KNOWN_DOTLESS


def _promise_location(text: str) -> Optional[str]:
    """First promised path (see _promise_match), location only — kept for callers/mirrors that
    want just the surface."""
    m = _promise_match(text)
    return m[0] if m else None


def _promise_match(text: str):
    """(location, start, end) for the first path that is the object/destination of an ACTIVE,
    FIRST-PERSON forward production promise, else None. A produce verb must GOVERN the path
    (verb before path, same clause, active) AND the verb's clause must be first-person or
    imperative. A past claim, a negated promise, a passive/copular frame, a conditional offer,
    a third-person/adverbial subject, a file-tree listing, or a path no produce verb governs
    (a mention, a noun-modifier) stay inert — that is what keeps the advance gate from
    false-firing on a non-commitment."""
    fenced = _fenced_spans(text)                  # scan fences ONCE, not per path
    for loc, a, b in detect_locations(text):
        if not _is_file_shaped(loc):
            continue                              # bare lowercase word -> prose, not a real file
        ls = text.rfind("\n", 0, a) + 1
        le = text.find("\n", b)
        if _non_prose_line(text[ls:le if le != -1 else len(text)]):
            continue                              # path sits in a file-tree diagram or table row
        if any(s <= a < e for s, e in fenced):
            continue                              # path sits inside a ```fenced code block``` -> code, not a promise
        if _PROPOSAL_MARK_RX.search(text[max(0, ls - 200):a]):
            continue                              # path sits under/within a proposal header ("Option A:", "New Task N", "worth building")
        bstart = max(0, a - _BIND_BEFORE)
        before = text[bstart:a]
        if _PAST_PRODUCE_RX.search(before):
            continue                              # "added X" -> completion, not a promise
        if _NEGATED_PROMISE_RX.search(before + " " + text[b:b + 8]):
            continue                              # "won't add X" -> retraction, not a promise
        mp = _PATH_PAREN_RX.match(text, b)
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
            line_pref = text[ls:bstart + vm.start()]
            if not _LINE_INITIAL_RX.match(line_pref) and not _FIRST_PERSON_RX.search(line_pref):
                continue                          # mid-line, no first-person subject -> not my promise
            return loc, a, b                      # a first-person/imperative produce verb governs path
    return None


# A clause boundary for QUANTITY scoping: sentence-ending punctuation only (a dot inside a
# dotted token — "v1.2", "e.g." — is not a boundary, same rule as _GOVERN_BREAK_RX's dot arm).
_QTY_CLAUSE_BREAK_RX = re.compile(r"[;:\n!?]|(?<!\b[A-Za-z])\.(?!\S)")


def _promise_clause(text: str, a: int, b: int) -> str:
    """The sentence containing the promise span [a, b) — the ONLY text a quantity may be read
    from. detect_quantity over the WHOLE message let an unrelated number in a later sentence
    ("That took 3 attempts across 5 runs.") change commitment_key, so re-stating the same
    promise opened a SECOND row for one obligation — the exact duplication the module docstring
    says the key prevents."""
    start = 0
    for m in _QTY_CLAUSE_BREAK_RX.finditer(text, 0, a):
        start = m.end()
    m = _QTY_CLAUSE_BREAK_RX.search(text, b)
    return text[start:m.start() if m else len(text)]


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
    pm = _promise_match(text)
    if not pm:
        return None
    loc, a, b = pm
    qmin, qmax = detect_quantity(_promise_clause(text, a, b)) or (None, None)
    return {"location": normalize_path(loc), "qty_min": qmin, "qty_max": qmax}


def _canon_qty(q):
    """An integral float reads as its int: detect_quantity yields floats (3.0), the qty_min/
    qty_max columns carry INTEGER affinity (3.0 stores as 3), so an un-canonicalized key was
    NOT re-derivable from the persisted row — commitment_key(s, loc, 3, 3) != the key recorded
    from (3.0, 3.0). One obligation, one key, whichever side derives it."""
    if isinstance(q, float) and q.is_integer():
        return int(q)
    return q


def commitment_key(session_id: str, location: str, qmin, qmax) -> str:
    raw = f"{session_id}\x00{normalize_path(location)}\x00{_canon_qty(qmin)}\x00{_canon_qty(qmax)}"
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
        "ON CONFLICT(commitment_key) DO UPDATE SET status = 'open', retract_param = NULL "
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

# === Retraction: surfaced-retraction detection + the reconcile decision (spec §4 — L2) ===
#
# A commitment is VALIDLY retracted only when the assistant EXPLICITLY drops it with a
# subject-bound reason: reconcile's closed parameter set (R = a recorded result that
# subject-binds the location, U = a real user contract change), or an explicit reason-bound
# descope surfaced in prose (surfaced_retraction_locations). A commitment that merely VANISHES
# with no surfaced reason is a HIDDEN retraction (detect_hidden_retraction) — exactly what the
# advance gate must still catch, never silently honor. Firewall: NORMALIZED-EQUALITY membership
# only (retracting cache.py never clears auth.py); fail-safe to the empty set on any internal
# error (never mass-clear, never crash the hook). Stdlib only; no LLM, no HTTP.
#
# Spec: docs/archive/specs/2026-05-31-makoto-bidirectional-falsifiability-design.md §4 (retraction).

def reconcile(commitment, *, reason_result_at=None, recorded=None,
              user_claims=False, contract_changed=False) -> str:
    """Decide whether an open commitment is VALIDLY retracted. Returns 'cleared'|'blocked'.

    Closed set of valid parameters:
      R = a recorded result whose key SUBJECT-BINDS (normalized equality) to the
          commitment location — proof the commitment is moot/impossible at its subject.
      U = the user changed the live contract section (a genuine supersession).
    Anything else stays blocked: an unbound reason (e.g. an empty fakeexcuse.txt that
    does not equal the commitment location), a forged user-claim with no contract
    change, or no verification at all. Hidden/unbound/unverified retractions never clear.
    """
    loc = commitment["location"]
    if reason_result_at is not None and recorded is not None:
        if subject_binds(loc, reason_result_at) and reason_result_at in recorded:
            return "cleared"                          # R: bound result proves it moot
        return "blocked"                              # unbound reason (the fakeexcuse firewall)
    if user_claims:
        return "cleared" if contract_changed else "blocked"   # U: only a real contract change
    return "blocked"


def detect_hidden_retraction(*, dropped: bool, reason) -> bool:
    """A commitment that VANISHES (dropped) with no surfaced reason is a HIDDEN
    retraction -> flag. A commitment still carried forward (not dropped) is not."""
    return bool(dropped) and not reason


# --- Surfaced retraction detection (the reconcile/retraction wiring) -----------------------
# Retraction vocab (_RETRACT_VERB_RX, _RETRACT_NEGPROMISE_RX, _RETRACT_POST_RX,
# _RETRACT_REASON_RX, _RETRACT_CLAUSE_BREAK_RX, _WRONG_SUBJECT_RX, _ACCIDENTAL_RX,
# _RETRACT_KEPT_RX, _RETRACT_ADVERSATIVE_RX) relocated to lexicons.py (L0) in Task 7.
# StopCheck functions and algorithm comments remain here.


def _fenced_spans(text: str):
    """Character ranges inside ``` code fences (quoted output, not the AI's own speech). Consumes the
    L0 single-source lexicons._FENCE_SPAN_RX (dedup U2) — the fence regex is defined in one place;
    substrate.claims._code_spans consumes the same object."""
    return [(m.start(), m.end()) for m in _FENCE_SPAN_RX.finditer(text)]


_RETRACT_COND_RX = re.compile(r"\b(if|unless|when|whether|assuming|in case)\b", re.I)
# Branch (2) has no retraction VERB to anchor _WRONG_SUBJECT_RX against, so a wrong subject
# reaches it as an ATTRIBUTION frame directly before the path: "<you|they|the linter|Alice>
# <said/reported/claims/...> cache.py is dropped" reports someone ELSE's drop — never the AI
# clearing its own commitment. Case-sensitive `[A-Z][a-z]+` mirrors _WRONG_SUBJECT_RX's
# proper-noun arm; the verb list is speech/report verbs only, so "As you requested, X is out
# of scope" (a genuine user supersession) still clears.
_POST_ATTRIB_RX = re.compile(
    r"(?:\byou\b|\bthey\b|\bthe\s+\w+|\b[A-Z][a-z]+)\s+"
    r"(?:said|says|say|reported|reports|claims?|claimed|notes?|noted|thinks?|thought|"
    r"suggests?|suggested|argues?|argued|mentions?|mentioned|believes?|believed|"
    r"wrote|writes|flags?|flagged|insists?|insisted)\s*$")
# The first SENTENCE of the after-window: a '?' in the same sentence as the post-positive
# predicate marks the whole frame interrogative, however far past 40 chars it lands.
_AFTER_SENTENCE_RX = re.compile(r"[.!\n]")
_RETRACT_MODAL_Q_RX = re.compile(
    r"^\s*(?:should|shall|can|could|may|would|do|does|did)\s+(?:i|we)\b", re.I)


def _retract_interrogative_or_conditional(pre: str, after: str) -> bool:
    """A question ("Should I skip X?") or a conditional ("if tests fail we drop X") is not an
    actual retraction decision."""
    clause = pre.rsplit(".", 1)[-1]
    return bool(_RETRACT_COND_RX.search(clause)
                or _RETRACT_MODAL_Q_RX.match(clause.strip())
                or "?" in after[:30])


def _retract_recommitted(text: str, loc: str, path_end: int) -> bool:
    """True if the SAME path is re-promised or produced AFTER its retraction (net still live):
    "going to skip X but I will add it", "un-dropping X — re-adding it now"."""
    tail = text[path_end:path_end + 180]
    base = re.escape(loc.rsplit("/", 1)[-1])
    return re.search(
        r"\b(?:re-?add\w*|add\w*|will add|keep\w*|ship\w*|implement\w*|creat\w*|"
        r"writ\w*|wrote|build\w*|built|includ\w*|restor\w*|put(?:ting)? (?:it )?back|"
        r"un-?drop\w*)\b[^.]{0,40}(?:" + base + r"|\bit\b)", tail, re.I) is not None


def surfaced_retraction_locations(text: str) -> set:
    """Return the set of normalized paths the assistant EXPLICITLY and REASON-BOUND retracts.

    Fail-safe: ANY internal error -> empty set (never mass-clear, never crash the hook)."""
    try:
        return _surfaced_retraction_locations(text or "")
    except Exception:
        return set()


def _surfaced_retraction_locations(text: str) -> set:
    if not text:
        return set()
    out = set()
    fenced = _fenced_spans(text)
    for loc, a, b in detect_locations(text):
        if any(s <= a < e for s, e in fenced):
            continue                                  # inside a code fence -> quoted output
        before = text[max(0, a - 80):a]
        after = text[b:b + 60]
        sentence = text[max(0, a - 120): b + 80]
        if _RETRACT_KEPT_RX.match(after):
            continue                                  # "X is still needed" -> explicitly KEPT
        has_reason = _RETRACT_REASON_RX.search(sentence) is not None
        bound = False
        # (1) an active retraction verb governing the path, same clause, before it, with reason
        for vm in _RETRACT_VERB_RX.finditer(before):
            between = before[vm.end():]
            if _RETRACT_CLAUSE_BREAK_RX.search(between) or _RETRACT_ADVERSATIVE_RX.search(between):
                continue                              # different clause / contrasted-away path
            pre = before[:vm.start()]
            if _NEG_FRAME_RX.search(pre[-40:]):
                continue                              # "not/never/n't ... skip" -> KEPT
            if _WRONG_SUBJECT_RX.search(pre[-25:]):
                continue                              # "you/they/the linter ... skip" -> not AI
            if _ACCIDENTAL_RX.search(pre[-40:]):
                continue                              # accidental loss, not a deliberate descope
            if _retract_interrogative_or_conditional(pre, after):
                continue
            if not has_reason:
                continue                              # bare drop, no reason -> HIDDEN, don't clear
            bound = True
            break
        # (1b) a negated production frame ("do not add X", "won't implement X") + reason
        if not bound and has_reason:
            for nm in _RETRACT_NEGPROMISE_RX.finditer(before):
                between = before[nm.end():]
                if _RETRACT_CLAUSE_BREAK_RX.search(between) or _RETRACT_ADVERSATIVE_RX.search(between):
                    continue
                pre = before[:nm.start()]
                if _WRONG_SUBJECT_RX.search(pre[-25:]):
                    continue                          # "you won't add X" -> not the AI's drop
                if _retract_interrogative_or_conditional(pre, after):
                    continue
                bound = True
                break
        # (2) a post-positive predicate after the path ("X is out of scope", "X can wait") —
        # under the SAME guards branch (1) applies. Un-guarded, this branch cleared a commitment
        # with no surfaced reason ("cache.py is dropped" -> cleared, while branch (1)'s twin
        # "I am dropping cache.py" correctly stayed open), honored someone else's drop ("the
        # linter reported cache.py is dropped", "you said cache.py is out of scope"), read an
        # accidental loss as a deliberate descope ("cache.py was dropped by mistake in the
        # rebase"), and cleared on an OPEN QUESTION whose '?' fell past the 40-char window
        # ("cache.py is out of scope, or should I still land it in this PR?").
        if not bound and has_reason:
            pm = _RETRACT_POST_RX.match(after)   # ^[\s,]* in the pattern already skips leading space
            first_sentence = _AFTER_SENTENCE_RX.split(after, 1)[0]
            if (pm
                    and not _NEG_FRAME_RX.search(after[:pm.end()])
                    and "?" not in first_sentence
                    and not _POST_ATTRIB_RX.search(before[-30:])
                    and not (_ACCIDENTAL_RX.search(before[-40:]) or _ACCIDENTAL_RX.search(after))
                    and not _retract_interrogative_or_conditional(before, after)):
                bound = True
        if not bound:
            continue
        if _retract_recommitted(text, loc, b):
            continue                                  # re-promised/produced after -> still live
        out.add(normalize_path(loc))
    return out
