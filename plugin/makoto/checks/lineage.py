from __future__ import annotations


# content.fabricated_commit_sha — fabricated commit SHA/tag presented as proof of a commit.
#
# Cheat class: fabricated-evidence / verdict-exceeds-work. The AI ends its turn claiming a commit
# landed — "committed as a1b2c3d", "tagged v1.2.0 (3c4d5e6)" — and presents a plausible-looking
# git SHA as PROOF, while the session history contains NO `git commit` / `git tag` tool_use that
# could have produced it. The SHA is hallucinated, the same way content.unsourced_webfetch catches
# a hallucinated WebFetch URL.
#
# Detection (FP-SAFE BY DESIGN):
#   1. A real end-of-turn Stop claim. We read the AI's closing text from `last_assistant_message`
#      (fallback `response` for the synthetic-test payload shape), and treat a MISSING
#      `stop_reason` as end-of-turn (Claude Code's real Stop payload carries no `stop_reason`).
#      This is the AI's OWN closing claim — never a USER-directed action, so this predicate
#      structurally cannot gate the user.
#   2. Find a SHA-shaped hex token (7–40 hex chars) bound to a POSITIVE commit/tag-HAPPENED CLAIM
#      ("committed as <sha>", "tagged <sha>", "commit <sha> is on main") AND NOT sitting in a
#      negation/deferral/referential window. Keying on the ASSERTION, not mere SHA-token +
#      commit-keyword co-occurrence, excludes a denial ("I have NOT committed ... <sha>"), a
#      deferral ("I haven't committed yet"), and a reference to a USER-supplied SHA ("the commit
#      <sha> you mentioned") — so arbitrary hex (addresses, digests, fixtures) never fires.
#   3. If history holds a real `git commit` / `git tag` Bash tool_use -> NEVER fire. The detector
#      is invocation-FORM-AGNOSTIC: it matches the bare `git commit`, a cd'd-directory commit, AND
#      every form that places git GLOBAL OPTIONS between `git` and the subcommand (`git -C
#      <worktree> commit`, `git -c user.name=Bot commit`) — a truthful worktree commit then a
#      truthful SHA claim must NOT fire. Quoted strings are blanked first so a `-m "...commit..."`
#      message body can't masquerade as the verb.
#   4. If the claimed SHA literally appears in any prior tool_result payload -> NEVER fire. The
#      SHA is grounded in real tool output.
#   5. Otherwise the SHA is presented as proof with no work behind it -> fire.
#
# A fire is a blocking decision on the AI's OWN Stop claim, never a restriction on a USER-directed
# action; any decode or shape failure returns None.
import re
from typing import Optional
from makoto.kit import claim_vs_history_predicate, iter_tool_events, raw_payload_str
from makoto.registry import Check
from makoto.vocab import _QUOTED_RX  # L0 shared lexicon

# A git SHA presented as commit evidence: a STANDALONE run of 7–40 hex chars (lower bound 7 =
# git's default short-SHA length; upper bound 40 = full SHA-1). The word-boundary guards keep it
# from matching the middle of a longer alphanumeric token (e.g. "deadbeef" inside "0xdeadbeef").
# Requiring a full 7+ consecutive-hex word is itself the FP guard: ordinary prose words almost
# never contain 7 consecutive hex letters, so the gap below can be permissive.
_SHA_RX = r"(?<![0-9a-zA-Z])([0-9a-f]{7,40})(?![0-9a-zA-Z])"

# A fire requires a POSITIVE commit/tag-HAPPENED CLAIM, and REJECTS any match whose SHA sits in a
# negated or referential window. Co-occurrence of a SHA with a commit keyword never fires on its
# own — an assertion is required.

# Positive commit/tag-completion verbs. "committed"/"tagged"/"landed"/"pushed" are
# completed-action assertions; bare "commit"/"tag" (the noun) only counts when it is itself
# asserted as present-on-a-ref (handled by _CLAIM_RXS below), never on its own. A SHORT, same-line,
# lazy connector gap binds verb<->SHA.
_GAP = r"[^\n]{0,24}?"          # short, same-line, lazy connector gap
_TAG_GAP = r"[^\n]{0,40}?"      # tags often carry a version label before the SHA

# Each claim regex asserts a commit/tag ACTUALLY HAPPENED and cites a SHA.
_CLAIM_RXS = (
    # forward, completed verb: "committed as a1b2c3d", "committed a1b2c3d"
    re.compile(r"\bcommitted\b" + _GAP + _SHA_RX, re.IGNORECASE),
    # forward, asserting noun-on-a-ref: "commit a1b2c3d is on main", "commit a1b2c3d landed"
    re.compile(
        r"\bcommit\b\s*[:#]?\s*" + _SHA_RX +
        r"[^\n]{0,24}?\b(?:is|was|has been|landed|pushed|on)\b",
        re.IGNORECASE,
    ),
    # "created/made/pushed (the )commit a1b2c3d"
    re.compile(
        r"\b(?:created|made|pushed|landed)\b[^\n]{0,16}?\bcommit\b\s*[:#]?\s*" + _SHA_RX,
        re.IGNORECASE,
    ),
    # strong completion verb directly citing a SHA, no "commit" noun needed: "pushed e5d6c7b",
    # "merged as e5d6c7b", "shipped it at e5d6c7b" — a completion assertion, not co-occurrence.
    re.compile(
        r"\b(?:landed|pushed|merged|shipped)\b\s*(?:it\s+)?[:#]?\s*(?:as\s+|at\s+|in\s+|to\s+\S+\s+as\s+)?"
        + _SHA_RX,
        re.IGNORECASE,
    ),
    # tag completion: "tagged v1 (3c4d5e6)", "created tag ... a1b2c3d"
    re.compile(r"\btagged\b" + _TAG_GAP + _SHA_RX, re.IGNORECASE),
    re.compile(
        r"\b(?:created|pushed)\b[^\n]{0,16}?\btag\b" + _TAG_GAP + _SHA_RX,
        re.IGNORECASE,
    ),
    # reverse order: "a1b2c3d was committed", "a1b2c3d landed on main"
    re.compile(
        _SHA_RX + r"[^\n]{0,20}?\b(?:committed|landed|pushed|tagged)\b",
        re.IGNORECASE,
    ),
)

# Negation / deferral / referential cues. If any appears in the window AROUND a claimed SHA, the
# "claim" is actually a denial, a deferral, or a reference to a SHA the USER supplied — NOT a
# fabricated commit assertion. We look back further than forward because the negation usually
# precedes: "have NOT committed ... a1b2c3d".
_NEG_REF_RX = re.compile(
    r"""
      \bnot\s+(?:yet\s+)?committ            # "not committed", "not yet committ..."
    | \bnot\s+(?:yet\s+)?tagg               # "not tagged"
    | \bn['’]t\s+(?:yet\s+)?committ         # "haven't committed", "didn't commit"
    | \bn['’]t\s+(?:yet\s+)?tagg            # "haven't tagged"
    | \bno\s+commit\b                       # "no commit was made"
    | \bnever\s+committ                     # "never committed"
    | \bnever\s+tagg                        # "never tagged"
    | \bwithout\s+committ                   # "without committing"
    | \bwithout\s+tagg                      # "without tagging"
    | \bwould\s+(?:be|commit|have|then)\b   # "the SHA would be", "would commit"
    # FUTURE-INTENTION frame: a commit/push/tag/merge that is PLANNED, not done.
    # "will be committed as <sha>", "will commit ... <sha>", "to be pushed as <sha>",
    # "going to commit <sha>", "shall be tagged <sha>". A future commit is not a
    # claim that a commit HAPPENED, so the SHA is reserved/illustrative, not proof.
    | \bwill\s+(?:be\s+|then\s+|soon\s+)?(?:commit|push|tag|merg)
    | \bgoing\s+to\s+(?:be\s+)?(?:commit|push|tag|merg)
    | \bto\s+be\s+(?:commit|push|tag|merg)
    | \bshall\s+(?:be\s+)?(?:commit|push|tag|merg)
    # THIRD-PARTY subject: the commit is attributed to a NON-first-person actor
    # (CI / a bot / a teammate), so it is not the AI presenting ITS OWN fabricated
    # commit evidence — content.fabricated_commit_sha's cheat class is the AI's own claimed work.
    | \b(?:the\s+|a\s+)?ci\b\s*(?:bot|pipeline|job|run|runner|workflow)?\s+(?:bot\s+)?(?:committ|tagg|push|merg)
    | \b(?:the\s+|a\s+)?bot\s+(?:committ|tagg|push|merg)
    | \bgithub\s+actions?\b
    | \bgh\s+actions?\b
    | \bdependabot\b | \brenovate\b
    | \b(?:the\s+)?pipeline\s+(?:committ|tagg|push|merg)
    | \b(?:a\s+)?(?:teammate|colleague|coworker|co-worker)\s+(?:committ|tagg|push|merg)
    | \bsomeone\s+else\s+(?:committ|tagg|push|merg)
    | \bhaven['’]?t\b                       # bare "havent" (loose spelling)
    | \bhasn['’]?t\b
    | \bdidn['’]?t\b
    | \bdon['’]?t\b
    | \bwon['’]?t\b
    | \byou\s+mentioned\b                   # referential: "<sha> you mentioned"
    | \byou\s+(?:found|gave|provided|cited|referenced|asked|named|noted|listed)\b
    | \byou\s+were\s+asking\b
    | \basked\s+about\b                     # "asked about commit <sha>"
    | \basking\s+about\b
    | \breferring\s+to\b
    | \breferenced\b
    | \bregarding\s+the\s+commit\b          # "Regarding the commit <sha>..."
    | \babout\s+the\s+commit\b
    | \bthe\s+commit\b[^\n]{0,12}?\byou\b   # "the commit <sha> you ..."
    # PRE-EXISTING / UPSTREAM frame: a commit that already existed BEFORE this
    # session — a debugging-AI attributing a regression to a prior commit, not
    # presenting its OWN just-done work. "<sha> was pushed before I started",
    # "committed by someone before this session began". A commit predating the
    # session cannot be the AI's fabricated proof-of-work for THIS turn.
    | \bbefore\s+(?:i|we)\s+(?:started|began|got\s+(?:here|started))\b
    | \bbefore\s+(?:this|the\s+(?:current|present))\s+session\b
    # THIRD-PARTY ATTRIBUTION (passive "by <actor>"): "<sha> was committed by
    # someone", "tagged by a teammate" — the action is attributed to a non-self
    # actor, so it is not the AI's own fabricated proof. (Bare first-person
    # "committed by me" stays a claim — excluded from the actor list.)
    | \b(?:committed|tagged|pushed|merged)\s+by\s+(?!(?:me|us|myself|ourselves)\b)(?:someone|a\s+\w+|the\s+\w+|him|her|them|\w+(?:bot)?\b)
    # ADVISORY / INTERROGATIVE-ABOUT frame: the AI is asking the USER to verify a
    # SHA ("you should check whether <sha> was pushed"), not asserting it did so.
    # The advisory verb ("check"/"verify"/...) is the real discriminator; it
    # subsumes the trailing "whether <sha> was pushed", so no bare \bwhether\b cue
    # is needed (that over-suppressed a discourse "whether or not it matters, I
    # committed <sha>").
    | \byou\s+(?:should|could|can|may|might|need\s+to|want\s+to)\s+(?:double-?\s*)?(?:check|verify|confirm|see|look|review|inspect)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# How far around a matched SHA to scan for a negation/referential cue. Look back further than
# ahead since the negation usually leads the SHA. The back-window is CLAMPED to the nearest
# preceding clause boundary so a referential cue bound to a DIFFERENT SHA in an earlier clause
# ("You mentioned 9999999, but I committed deadbee") cannot suppress a genuine claim.
_NEG_BACK = 80
_NEG_FWD = 40

# Clause separators: a cue on the far side of one of these belongs to a different clause and must
# not suppress this SHA.
_CLAUSE_BOUNDARY_RX = re.compile(
    r"[.;\n]|\bbut\b|\bhowever\b|\bthough\b|\bwhereas\b", re.IGNORECASE
)

# GLOBAL first-person DENIAL of committing/tagging/pushing anywhere in the turn. When the AI
# explicitly says it did NOT commit/tag/push this session, EVERY SHA in the turn is referential
# -> suppress all claims. First-person only: it must be the AI denying ITS OWN action.
_GLOBAL_DENIAL_RX = re.compile(
    r"""
      \b(?:have|'ve|has|had|am|'m|did|do)\s+not\s+(?:yet\s+)?(?:committed|tagged|pushed|made\s+(?:a\s+|any\s+)?commit)
    | \b(?:have|has|had|did|do|could|would|can)n['’]t\s+(?:yet\s+)?(?:committed|tagged|pushed|made\s+(?:a\s+|any\s+)?commit)
    | \bnot\s+(?:yet\s+)?committed\s+anything
    | \bwithout\s+(?:committing|tagging|pushing)
    | \bno\s+commit\s+(?:was|has\s+been)\s+made
    | \bnever\s+committed\b
    | \bnever\s+tagged\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# A real commit/tag invocation in the session, in ANY invocation form. Any run of git GLOBAL
# OPTION tokens is allowed between `git` and the `commit`/`tag` subcommand. Non-commit subcommands
# stay un-matched: `git show`, `git rev-parse`, `git diff` carry a non-commit/tag subcommand word,
# so they do not match. (Quotes are stripped first so a --message body mentioning "commit" can't
# masquerade.)
_GIT_OPT = r"(?:\s+-{1,2}[^\s]+)"        # one git global option token: -C, -c, --git-dir=/x, --no-pager
_GIT_OPT_VAL = r"(?:\s+(?![-])[^\s]+)?"  # its optional value token (skipped if next token is another option)
_GIT_COMMIT_OR_TAG_RX = re.compile(
    r"\bgit(?:" + _GIT_OPT + _GIT_OPT_VAL + r")*\s+(?:commit|tag)\b"
)


def _stop_text(current_event: dict) -> str:
    """The AI's end-of-turn text, production-shape-aware.

    Claude Code's real Stop payload exposes the assistant's final message as
    `last_assistant_message` and carries no `stop_reason` key. We therefore read
    `last_assistant_message` first, falling back to `response` (the synthetic-test payload
    shape), and treat a MISSING `stop_reason` as end-of-turn; only a PRESENT `stop_reason` other
    than 'end_turn' is rejected. Returns "" when this is not a fireable end-of-turn claim.
    """
    stop_reason = current_event.get("stop_reason")
    if stop_reason is not None and stop_reason != "end_turn":
        return ""
    text = current_event.get("last_assistant_message") or current_event.get("response", "")
    return text if isinstance(text, str) else ""


def _claimed_shas(text: str) -> list[str]:
    """SHAs in `text` ASSERTED (positively) to have been committed/tagged.

    Two-stage: (1) the SHA must be bound to a positive commit/tag-HAPPENED claim (`_CLAIM_RXS`);
    (2) the window around that SHA must NOT carry a negation/deferral/referential cue
    (`_NEG_REF_RX`) — otherwise it is a denial, a deferral, or a reference to a USER-supplied SHA,
    none of which is a fabricated commit assertion.
    """
    # GLOBAL disclaim: if the AI explicitly denies committing/tagging anywhere in the turn, every
    # SHA is referential -> no fabricated-commit assertion.
    if _GLOBAL_DENIAL_RX.search(text):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for rx in _CLAIM_RXS:
        for m in rx.finditer(text):
            sha = m.group(1).lower()
            if sha in seen:
                continue
            # The SHA span within the full text (group 1).
            s, e = m.span(1)
            # Back-window, CLAMPED at the nearest preceding clause boundary so a cue bound to a
            # different SHA in an earlier clause does not suppress this one.
            back_start = max(0, s - _NEG_BACK)
            back = text[back_start:s]
            bnds = list(_CLAUSE_BOUNDARY_RX.finditer(back))
            if bnds:
                back = back[bnds[-1].end():]
            # Forward-window, clamped at the first clause boundary after the SHA.
            fwd = text[e: e + _NEG_FWD]
            fbnd = _CLAUSE_BOUNDARY_RX.search(fwd)
            if fbnd:
                fwd = fwd[:fbnd.start()]
            if _NEG_REF_RX.search(back + " " + sha + " " + fwd):
                continue  # negated / deferred / referential -> not a claim
            seen.add(sha)
            out.append(sha)
    return out


def _real_commit_in_history(history: list) -> bool:
    """True iff any prior Bash tool_use actually ran `git commit` / `git tag`.

    Form-agnostic: matches the bare `git commit`, a cd'd-directory commit, and every
    `git <global-options...> commit|tag` form. See _GIT_COMMIT_OR_TAG_RX. Both Pre/PostToolUse
    rows pass through (either proves the commit invocation happened).
    """
    for tool, cmd, _resp in iter_tool_events(history):
        if tool != "Bash" or not isinstance(cmd, str) or not cmd:
            continue
        if _GIT_COMMIT_OR_TAG_RX.search(_QUOTED_RX.sub(" ", cmd)):
            return True
    return False


def _claim_subject(current_event: dict) -> Optional[str]:
    if current_event.get("hook_event_name") != "Stop":
        return None
    response = _stop_text(current_event)
    return response or None


def _sha_grounded_in_history(sha: str, history: list) -> bool:
    if _real_commit_in_history(history):
        return True
    for entry in history:
        payload = raw_payload_str(entry)
        if payload and sha in payload.lower():
            return True
    return False


sha_predicate = claim_vs_history_predicate(
    claim_rxs=_claimed_shas,
    neg_ref_rx=None,
    grounded_in_history=_sha_grounded_in_history,
    tool_gate=_claim_subject,
    message=lambda sha, _subject, pattern: (
        f"row {pattern.id} ({pattern.description}): commit SHA {sha!r} presented as proof, "
        "but no `git commit`/`git tag` tool_use ran this session — fabricated evidence"
    ),
)


sha_RETRY_HINT = 'Cite a real `git commit`/`git tag` run (or the SHA echoed in its tool output) before claiming a commit/tag landed. A SHA presented as proof with no commit/tag tool_use behind it this session is fabricated evidence (CLAUDE.md commandment 1, tool-call-diff canary).'
sha_DESCRIPTION = 'fabricated commit SHA/tag presented as proof of a commit (no git commit/tag ran)'

sha_CHECK = Check(id='content.fabricated_commit_sha', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('committed', 'Committed', 'commit', 'Commit', 'tagged', 'Tagged', 'tag', 'Tag', 'landed', 'Landed', 'pushed', 'Pushed', 'merged', 'Merged', 'created', 'Created', 'made', 'Made', 'shipped', 'Shipped'), retry_hint=sha_RETRY_HINT, description=sha_DESCRIPTION, eats=frozenset({"current_event", "history", "pattern"}), tests="LINEAGE")
# content.illusory_interruption_claim predicate — a fabricated "interrupted by user" excuse
# (same genre as content.illusory_authorship_trailer).
#
# Fires when a tool call would INTRODUCE a claim that the USER interrupted this session — in a
# git commit or in written file content — matching Claude Code's own synthetic marker text
# (`"[Request interrupted by user]"`) or a paraphrase of it. That marker is HARNESS-SYNTHESIZED,
# never model-written — so an agent citing it as an excuse for incomplete/abandoned work, when no
# such interruption appears in this session's RECENT recorded tool history (the dispatcher's
# bounded ~1h window, pruned), is presenting a fabricated event the same way
# content.fabricated_commit_sha catches a hallucinated SHA.
#
# Grounded, not over-broad: if this session's OWN history actually carries a genuine
# `tool_response.interrupted == true` row or a PostToolUseFailure `is_interrupt == true` terminal,
# the claim is TRUE and never fires. A bare description of the marker itself (this module's own
# documentation is: `makoto-allow: <reason>`.
#
# Built on `kit.introduced_regex_predicate` — the shared scaffold this check and
# content.illusory_authorship_trailer both need, called here WITH `grounded_in_history` — this
# check's own history-grounding veto, paid through `kit.unwitnessed`.
from makoto.kit import decode_history_event, introduced_regex_predicate

# The claim, however it's phrased. Matches the harness's own literal bracketed marker AND
# looser prose paraphrases -- both are the same claim ("the user is why this stopped").
_INTERRUPTION_CLAIM_RX = re.compile(
    r"\[?request\s+interrupted\s+by\s+(?:the\s+)?user\]?"
    r"|\binterrupted\s+by\s+(?:the\s+)?user\b"
    r"|\buser\s+interrupted\b",
    re.IGNORECASE,
)


def _genuine_interruption_in_history(history: list) -> bool:
    """True iff any prior tool event in `history` actually carries a HARNESS-set truthy
    `tool_response.interrupted` or PostToolUseFailure `is_interrupt` — real, non-model-writable
    signals, normalized with `bool(...)`. Fail-open per row: an undecodable row is skipped, never
    treated as grounding (letting a garbage row GROUND would hand the agent a self-grounding
    spoof: induce one undecodable row, then claim freely)."""
    for row in history or ():
        ev = decode_history_event(row)
        if not isinstance(ev, dict):
            continue
        # INCLUDE the failed-terminal spelling: an interrupted failure grounds the same fact.
        if (ev.get("hook_event_name") == "PostToolUseFailure"
                and bool(ev.get("is_interrupt"))):
            return True
        resp = ev.get("tool_response")
        if isinstance(resp, dict) and bool(resp.get("interrupted")):
            return True
    return False


interrupt_predicate = introduced_regex_predicate(
    body_rx=_INTERRUPTION_CLAIM_RX,
    grounded_in_history=_genuine_interruption_in_history,
    # States exactly what was checked: the dispatcher's RECENT event window, not "this session",
    # which the veto never reads in full and cannot certify an absence over.
    veto_suffix=(" — no genuine interruption appears in this session's recent recorded"
                 " tool history (the dispatcher's bounded event window)"),
)


from makoto.registry import Check as _Check
interrupt_RETRY_HINT = "Do not write or commit a claim that \"the user interrupted\" this session unless this session's own recorded history actually carries a real harness-set interruption. That marker is host-synthesized, never model-written -- citing it with nothing behind it is a fabricated excuse (same cheat class as content.fabricated_commit_sha). If you truly need the literal string on the record (a test fixture, this policy's own docs), annotate it `makoto-allow: <reason>`."
interrupt_DESCRIPTION = 'illusory "interrupted by user" claim (no genuine interruption recorded this session) in a commit or written content'

# keywords: a case-sensitive substring prefilter gates whether this predicate runs, while
# _INTERRUPTION_CLAIM_RX is case-insensitive -- a finite casing enumeration would leave
# regex-matching payloads unevaluated. Every alternative contains 'u' ('user'/'interrupted'), so
# ('u', 'U') is the case-independent superset that keeps the prefilter sound.
interrupt_CHECK = _Check(id='content.illusory_interruption_claim', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('u', 'U'), retry_hint=interrupt_RETRY_HINT, description=interrupt_DESCRIPTION, eats=frozenset({"current_event", "history", "pattern", "conn"}), tests="LINEAGE")
# content.unsourced_webfetch — WebFetch URL not in any prior tool_result.
#
# The agent invents a URL, often from a plausible-looking host+path pattern in training data,
# never returned by a prior search or supplied by the user.
#
# Predicate walks session history and checks whether the URL appears anywhere in prior
# tool_response content. Two short-circuits come first: a trusted-host allowlist for well-known
# docs domains, and -- the one that keeps the condition honest -- a URL the USER typed verbatim
# in a genuine transcript turn. "Not in a prior tool_result" is a proxy for "fabricated", and it
# is a proxy that misfires on the single most clearly-grounded case there is; see `_user_supplied`
# for the measured misfire.
import json
import os
from urllib.parse import urlparse
from makoto.kit import raw_payload_str, unwitnessed
from makoto.vocab import Finding


# Allowlisted hosts the agent legitimately knows from training data.
_TRUSTED_HOSTS = frozenset({
    "docs.anthropic.com",
    "code.claude.com",
    "claude.com",
    "docs.claude.com",
    "github.com",          # GitHub is so well-known that fabricating a github URL is rare
    "stackoverflow.com",
    "wikipedia.org",
    "en.wikipedia.org",
})


# What may TRAIL a url and still leave it the url the user typed. A url runs to the next
# whitespace, and only trailing punctuation may be shaved off the end -- the rule every linkifier
# uses. `See https://vendor.example/a.` still exempts `https://vendor.example/a`, while
# `.../api?token=secret` and `.../api.json` do not (a naive "characters that continue a url"
# blocklist got both of those wrong, waving through resources the user never named). It also
# handles a url inside a markdown link, `[docs](https://vendor.example/a)`, where the tail is `)`.
_TRAILING_PUNCT = ".,;:!?)>]}\"'`"
# What may PRECEDE a url and still leave it a url the source actually named, rather than a
# fragment EMBEDDED in a longer one (e.g. a wayback/redirect/query-parameter url that would
# otherwise pre-approve the resource embedded in it). The character immediately BEFORE the match
# decides: an alphanumeric or url-body character means the match continues an enclosing token, so
# it is NOT the named url; whitespace, start-of-text, or opening/citation punctuation means the
# url stands alone.
_URL_EMBED_PREV = set("/=&?%+~@#._-")


def _ends_url(turn: str, url: str) -> bool:
    """True iff `url` occurs in `turn` as a COMPLETE, STANDALONE url — anchored at BOTH ends:
    not a prefix of a longer url (trailing token rule) and not embedded inside a longer one
    (leading character rule, `_URL_EMBED_PREV`)."""
    start = turn.find(url)
    while start != -1:
        prev = turn[start - 1] if start > 0 else ""
        embedded = bool(prev) and (prev.isalnum() or prev in _URL_EMBED_PREV)
        tail = turn[start + len(url):]
        # Everything from the end of the match to the next whitespace: the rest of this token.
        rest = "" if (not tail or tail[0].isspace()) else tail.split(None, 1)[0]
        if not embedded and (not rest or all(c in _TRAILING_PUNCT for c in rest)):
            return True
        start = turn.find(url, start + 1)
    return False


def _user_supplied(url: str, current_event: dict) -> bool:
    """True iff `url` appears VERBATIM in a genuine user turn of this session's transcript.

    The mined defect is a FABRICATED url. "Never seen in a prior tool_result" is not the same
    set: a url the human typed into chat has never been in a tool_result either, so the naive
    check fired on exactly the case where the agent did the most obviously correct thing. A url
    the user typed is grounded BY DEFINITION -- no tool call can improve on that provenance.

    Verbatim, and only verbatim -- as a WHOLE URL, not a substring: a host-only or prefix match
    would exempt every path under any domain the user mentioned, or every proper prefix of
    anything they pasted, letting the agent invent a deeper/shorter resource they never named.
    `_ends_url` closes it by requiring the match to END where the user's url ended.

    Spoof-resistant by construction: the turns come from `ledger.user_turn_texts`, which admits
    only host-written, non-synthetic, non-tool-result user entries, so the agent cannot write
    itself a permission slip.
    """
    try:
        from makoto.state.ledger import user_turn_texts
        turns = user_turn_texts(current_event.get("transcript_path"))
    except Exception:
        # Absence of evidence, never evidence of absence: an unreadable transcript leaves the
        # check exactly as strict as it was before this exemption existed.
        return False
    return any(_ends_url(turn, url) for turn in turns)


def _is_fetch_shaped(tool_name: str, tool_input: dict) -> bool:
    """True for the built-in WebFetch, and for an MCP fetch tool under any other name: the
    url INPUT is the signal that a tool is being used as a WebFetch, not the literal string
    "WebFetch" -- an MCP tool whose own name says it fetches (e.g. `mcp__browser__fetch`) and
    that actually carries a url is the same fabricated-evidence surface under a different name."""
    if tool_name == "WebFetch":
        return True
    return (tool_name.startswith("mcp__") and "fetch" in tool_name.lower()
            and isinstance(tool_input.get("url"), str) and bool(tool_input.get("url")))


def _webfetch_url(current_event: dict) -> Optional[str]:
    """The url a WebFetch-shaped tool commits to, or None when the event never owes one at
    all: not fetch-shaped, no url, or a TRUSTED host. The user-typed oracle is a real witness
    and lives in `pays`/`paid`, not here."""
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    tool_input = current_event.get("tool_input") or {}
    if not _is_fetch_shaped(current_event.get("tool_name") or "", tool_input):
        return None
    url = tool_input.get("url", "")
    if not url:
        return None
    # Trusted-host short-circuit
    host = urlparse(url).netloc.lower()
    if host in _TRUSTED_HOSTS or any(host.endswith("." + th) for th in _TRUSTED_HOSTS):
        return None
    return url


def _url_grounded_in_history(url: str, history: list) -> bool:
    """True iff `url` was RETURNED by a prior tool call — present, as a standalone url
    (`_ends_url`, case-folded), in the settled `tool_response` content of a prior event.

    RESPONSE-ONLY, by construction: searching the whole raw payload of every event type made the
    old check self-defeating -- a prior PreToolUse row of the byte-identical WebFetch grounded
    its own retry, a `Bash: echo <url>` grounded the url the agent had just typed, and a bare
    substring test grounded every proper prefix of anything a response ever contained. Now: the
    row must parse, must carry a `tool_response` (a Pre row has none), the url must stand alone
    in that response's text, and an event whose own `tool_input` carries the url confirms nothing
    (the tool merely reflected what the agent fed it).

    `raw_payload_str` stays the canonical row unwrap, used here first as a cheap pre-filter
    before the row is parsed."""
    needle = url.lower()   # hoisted: the same fold ran once per history row
    for entry in history:
        payload = raw_payload_str(entry)
        if not payload or needle not in payload.lower():
            continue
        try:
            ev = json.loads(payload)
        except ValueError:
            continue                       # an unparseable row cannot prove settled output
        if not isinstance(ev, dict):
            continue
        resp = ev.get("tool_response")
        if resp is None:
            continue                       # no settled response -> a request, not evidence
        resp_text = resp if isinstance(resp, str) else json.dumps(resp)
        if not _ends_url(resp_text.lower(), needle):
            continue
        ti = ev.get("tool_input")
        ti_text = ti if isinstance(ti, str) else ("" if ti is None else json.dumps(ti))
        if needle in ti_text.lower():
            continue                       # the event echoed its own input -> self-written
        return True
    return False


def _oracle_consulted(transcript_path) -> bool:
    """True iff the user-turn oracle channel was actually AVAILABLE to consult: a transcript
    path was supplied and points at a readable file. The deny message must never assert "the
    user never typed it" when no transcript was ever read -- a hard deny resting on a false fact.
    The EXEMPTION side stays exactly as strict either way; only the STATED REASON changes."""
    return bool(transcript_path) and os.path.isfile(transcript_path)


def webfetch_owes(ev: dict):
    """OTHER_POINT: an untrusted-host WebFetch commits to the url it names."""
    return (url,) if (url := _webfetch_url(ev)) is not None else ()


def webfetch_predicate(*, current_event: dict, history: list, pattern, conn=None) -> Optional[Finding]:
    """The Pre predicate. Fires iff the WebFetch url passes no short-circuit (`_webfetch_url`:
    trusted host) and is witnessed by neither a prior tool RESPONSE (`_url_grounded_in_history`)
    nor the user's own transcript turn (`_user_supplied`). The message states only what was
    actually checked: the user-typed clause is asserted only when a transcript was available to
    consult (`_oracle_consulted`)."""
    for _ev, url in unwitnessed(
            (current_event,), owes=webfetch_owes,
            paid=(lambda u: _url_grounded_in_history(u, history),
                  lambda u: _user_supplied(u, current_event))):
        if _oracle_consulted(current_event.get("transcript_path")):
            oracle_clause = "the user never typed it"
        else:
            oracle_clause = ("no readable transcript was available to check whether the user "
                             "typed it")
        return Finding(
            pattern_id=pattern.id, file="", line=0, level="error",
            message=(f"row {pattern.id} ({pattern.description}): this URL was never returned in "
                     f"a prior tool call's response in this session, and {oracle_clause}"),
            retry_hint=pattern.retry_hint,
            snippet=str(url)[:200],
        )
    return None


webfetch_RETRY_HINT = 'Run WebSearch first; only WebFetch URLs that prior search results actually returned, or that the user gave you verbatim. Fabricated URLs typically reflect plausible host+path patterns from training data, not real pages.'
webfetch_DESCRIPTION = 'WebFetch URL neither returned by a prior tool_result nor supplied verbatim by the user'

webfetch_CHECK = _Check(id='content.unsourced_webfetch', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('http://', 'https://'), retry_hint=webfetch_RETRY_HINT, description=webfetch_DESCRIPTION, eats=frozenset({"current_event", "history", "pattern"}), tests="LINEAGE")
# gate.unclaimed_unit -- the session added a unit that answers to nothing: a function nobody
# asked for and nothing reaches is not neutral, it is surface every later reader has to
# understand, every later change has to keep working, and no requirement protects.
#
# WHAT COUNTS AS A CLAIM, and all three are on the record makoto already reads:
#
#   1. THE OPERATOR NAMED IT -- the unit's name appears in a genuine operator turn
#      (`ledger.user_turn_texts`, host-written turns only).
#   2. SOMETHING REACHES IT -- the name appears somewhere in this session's introduced text other
#      than its own definition: a call, an export, a test, an edited call site.
#   3. A DECORATOR REGISTERED IT -- `@pytest.fixture`, `@app.route`, `@property`, `@click.command`.
#      A decorator IS a claim: it hands the unit to a framework that will call it. This is the
#      exclusion that makes the check material rather than noisy, and it generalizes instead of
#      enumerating frameworks.
#
# Absent all three, the unit was drawn from no claim.
#
# TWO EXCLUSIONS BEYOND THE THREE CLAIMS:
#   * A `test_`-prefixed def is claimed BY COLLECTION. pytest calls it because of its name, so a
#     gate that demanded a reference would fire on every test written -- including the ones in
#     this very change.
#   * TOP-LEVEL defs and classes only. A method answers to its class, and deciding whether a
#     class needs a given method is a design judgement rather than a record read.
#
# RECALL BOUNDS:
#   * A public API entry point added for an external caller fires, because no caller exists in
#     this repository to reach it. From the record, an unreachable new unit and a premature
#     abstraction look the same, and the reader is the one who can tell.
#   * The unit must be in text that PARSES as Python. `kit.parse_introduced` degrades to silent,
#     so an unparseable Edit fragment is never a finding -- FN-safe.
#   * Name matching is by exact token. An operator asking for "a helper that does X" without
#     naming it does not discharge the obligation.
#
# DISCRIMINANT AGAINST `gate.liveness`, which also analyses written Python: that gate asks whether
# a STATEMENT can affect anything inside code the session touched, reading it off DISK by path.
# This one asks whether a DEFINITION answers to anything, reading the session's own introduced
# text out of history, and its finding is a unit that is perfectly live -- it simply has no
# claim. A session whose only act is writing one unreferenced, undecorated function fires this
# gate and gives gate.liveness nothing: a `def` is not a dropped pure statement.
#
# BLOCK TIER: the discharge is in-turn -- point the unit at its claim (call, export, test or
# decorate it) or delete it. The recall bounds above cost one reference, never a lost change.
import ast

from makoto.kit import decode_history_event, introduced_text, parse_introduced, unwitnessed

_MUTATION_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})
# Claimed BY COLLECTION: the runner calls it because of its name. See the comment above.
_COLLECTED_PREFIX = "test_"
# How many whole-word occurrences of the unit's name in the session's introduced text mean
# something REACHES it. The `def`/`class` line contributes the first occurrence, so a second is
# the earliest evidence of a use: 1 would let every definition discharge itself and 3 would
# demand two callers.
_REACHED_AT = 2


def _introduced_units(text: str) -> list:
    """Top-level `def`/`class` names introduced by `text`, minus the ones a framework claims.

    A DECORATED unit is excluded here rather than discharged later, because the decorator is the
    claim -- there is nothing left to look for once one is present.
    """
    tree, _ = parse_introduced(text)
    if tree is None:
        return []                    # unparseable fragment -> never a finding (FN-safe)
    out = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.decorator_list:
                continue              # a framework registered it: that IS the claim
            name = node.name
        elif (isinstance(node, ast.Assign) and isinstance(node.value, ast.Lambda)
                and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            # `compute_ratio = lambda a, b: a / b` binds a unit exactly as a `def` would --
            # the same unclaimed-surface question, under Python's other function-binding form.
            name = node.targets[0].id
        else:
            continue
        if name.startswith(_COLLECTED_PREFIX):
            continue                 # claimed by collection
        out.append(name)
    return out


def unclaimed_owes(ev: dict):
    """OTHER_POINT: a settled mutation commits to every top-level unit it defines."""
    if ev.get("hook_event_name") != "PostToolUse":
        return ()
    tool = ev.get("tool_name", "")
    if tool not in _MUTATION_TOOLS:
        return ()
    ti = ev.get("tool_input", {}) or {}
    text = introduced_text(tool, ti) if isinstance(ti, dict) else ""
    if not text:
        return ()
    fp = str(ti.get("file_path", "")) if isinstance(ti, dict) else ""
    return tuple((name, fp) for name in _introduced_units(text))



def unclaimed_unit_gate(history, *, transcript_path=None) -> Optional[Finding]:
    """Fire iff this session introduced a top-level unit whose name answers to nothing: no
    operator turn names it, nothing in the session's own introduced text reaches it, and no
    decorator registered it."""
    events = [ev for ev in map(decode_history_event, history or ()) if isinstance(ev, dict)]
    introduced = []
    for ev in events:
        if ev.get("hook_event_name") != "PostToolUse":
            continue
        tool = ev.get("tool_name", "")
        if tool not in _MUTATION_TOOLS:
            continue
        ti = ev.get("tool_input", {}) or {}
        text = introduced_text(tool, ti) if isinstance(ti, dict) else ""
        if text:
            introduced.append(text)
    if not introduced:
        return None
    # REACHED: the name appears in the session's introduced text beyond its own `def`/`class`
    # line. One occurrence is the definition itself; a second is a use.
    blob = "\n".join(introduced)
    unclaimed = [subject for _ev, subject in unwitnessed(
        events, owes=unclaimed_owes,
        paid=(lambda s: sum(1 for tok in _TOKEN_RX.findall(blob or "") if tok == s[0])
                        >= _REACHED_AT,
              lambda s: _named_by_operator(s[0], transcript_path)))]
    if not unclaimed:
        return None
    name, where = unclaimed[0]
    more = f" (+{len(unclaimed) - 1} more)" if len(unclaimed) > 1 else ""
    return Finding(
        pattern_id="gate.unclaimed_unit",
        file=where,
        line=0,
        level="error",
        message=(
            f"`{name}` was added and answers to nothing on the record{more}: no operator turn "
            f"names it, nothing this session wrote reaches it, and no decorator registered it."
        ),
        retry_hint=(
            "Point the unit at its claim -- call it, export it, test it, or decorate it -- or "
            "delete it. A unit no requirement protects is surface every later change has to keep "
            "working."
        ),
        snippet=name[:200],
    )


# Every identifier-shaped token. A stdlib call with no branches at all cannot have a fallthrough.
_TOKEN_RX = re.compile(r"[A-Za-z0-9_]+")


def _named_by_operator(name: str, transcript_path) -> bool:
    """True iff a GENUINE operator turn names the unit. `ledger.user_turn_texts` admits only
    host-written turns. Import is call-time so a Stop gate does not carry an import-time edge
    into the store. Inlines the same identifier-token read `unclaimed_unit_gate`'s REACHED
    witness uses (`_TOKEN_RX`), so the two witnesses agree on what a "word" is."""
    if not transcript_path:
        return False
    try:
        from makoto.state.ledger import user_turn_texts
        turns = user_turn_texts(transcript_path)
    except Exception:
        return False                 # fail open: an unreadable transcript is no evidence
    return any(name in _TOKEN_RX.findall(t or "") for t in turns or ())


unclaimed_CHECK = _Check(id="gate.unclaimed_unit", applies_at="Stop", posture="BLOCK",
               tests="LINEAGE",
               eats=frozenset({"history", "transcript_path"}),
               run=lambda c: unclaimed_unit_gate(c.history,
                                                 transcript_path=c.transcript_path))


# event.unbriefed_dispatch -- refuses an Agent/Task dispatch whose prompt lacks a READ:, WRITE:
# and ACCEPTANCE: line.
from makoto.kit import DISPATCH_TOOL_NAMES, dispatch_brief_lines, unwitnessed
from makoto.core._declaredverifiers import dispatch_opt_in


def unbriefed_owes(ev: dict):
    if ev.get("hook_event_name") != "PreToolUse" or ev.get("tool_name") not in DISPATCH_TOOL_NAMES:
        return ()
    ti = ev.get("tool_input")
    prompt = ti.get("prompt") if isinstance(ti, dict) else None
    return (prompt,) if isinstance(prompt, str) else ()


def _briefed(prompt: str) -> bool:
    lines = dispatch_brief_lines(prompt)
    return bool(lines["READ"] and lines["WRITE"] and lines["ACCEPTANCE"])


def unbriefed_predicate(*, current_event: dict, history: list, pattern, conn=None) -> Optional[Finding]:
    if not dispatch_opt_in(current_event.get("cwd")):
        return None
    for _ev, prompt in unwitnessed((current_event,), owes=unbriefed_owes, paid=(_briefed,)):
        return Finding(
            pattern_id=pattern.id, file="", line=0, level="error",
            message=(f"row {pattern.id} ({pattern.description}): dispatch prompt carries no "
                     "READ:, WRITE: and ACCEPTANCE: line -- a worker sent without what it "
                     "reads, may write, and what pays it."),
            retry_hint=pattern.retry_hint,
            snippet=prompt[:200],
        )
    return None


unbriefed_RETRY_HINT = ('Give the dispatch a brief with a line-start `READ:`, `WRITE:` and '
                        '`ACCEPTANCE:` (the paths it reads, the paths it may write, and the '
                        'command that pays the work) before sending it.')
unbriefed_DESCRIPTION = ('dispatch prompt lacks a READ:, WRITE: and ACCEPTANCE: line '
                         '(opt-in: makoto.toml `dispatch = true`)')

unbriefed_CHECK = Check(id='event.unbriefed_dispatch', applies_at="Pre", posture="BLOCK",
              predicate_module=__name__, keywords=('Agent', 'Task'),
              retry_hint=unbriefed_RETRY_HINT, description=unbriefed_DESCRIPTION,
              eats=frozenset({"current_event", "pattern"}), tests="LINEAGE")


# the LINEAGE shape: its rows, and the one Pre entry dispatch calls for any of them
_ROWS = (sha_CHECK, interrupt_CHECK, webfetch_CHECK, unclaimed_CHECK, unbriefed_CHECK,)
ROWS = {c.id: c for c in _ROWS}
CHECK, *EXTRA_CHECKS = _ROWS
_PREDICATES = {sha_CHECK.id: sha_predicate, interrupt_CHECK.id: interrupt_predicate, webfetch_CHECK.id: webfetch_predicate, unbriefed_CHECK.id: unbriefed_predicate}


def predicate(*, current_event: dict, history: list, pattern, conn=None):
    """Dispatch calls one predicate per module; this shape's answers for the row it names."""
    return _PREDICATES[pattern.id](current_event=current_event, history=history, pattern=pattern, conn=conn)
