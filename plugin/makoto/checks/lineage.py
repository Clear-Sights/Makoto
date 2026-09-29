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
#   2. Find a SHA-shaped hex token (7–40 hex chars) in a clause that places it in git history
#      ("committed as <sha>", "tagged <sha>", "on main as <sha>") AND NOT sitting in a
#      negation/deferral/referential window. The window excludes a denial ("I have NOT committed ... <sha>"), a
#      deferral ("I haven't committed yet"), and a reference to a USER-supplied SHA ("the commit
#      <sha> you mentioned") — so arbitrary hex (addresses, digests, fixtures) never fires.
#   3. If history holds a real `git commit` / `git tag` Bash tool_use that CREATES an object (not a
#      read-only `git tag -l`, not `commit --dry-run`) -> NEVER fire. The detector
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
from makoto.vocab import _lazy_re
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

# A SHA is CLAIMED when the clause it sits in places it in git history: the clause carries commit/
# tag vocabulary ("committed as", "commit <sha> is on", "tagged v1 (<sha>)", "landed/pushed/merged/
# shipped <sha>") or names a ref it sits on ("on main as <sha>", "<sha> is at HEAD"). One reading of
# the effect -- a SHA presented as a commit -- rather than a list of verb-to-SHA spellings. A clause
# ends at a sentence stop followed by space, a newline, or a contrast word, so a version label
# (`v1.2.0`) does not cut its own clause.
_CLAUSE_RX = _lazy_re(r"[.;!?](?=\s|$)|\n|\bbut\b|\bhowever\b|\bthough\b|\bwhereas\b",
                      re.IGNORECASE)
_HISTORY_CUE_RX = _lazy_re(
    r"\b(?:commit\w*|tag(?:ged|s)?|landed|pushed|merged|shipped)\b"
    r"|\b(?:on|to|in|into|at)\s+(?:the\s+)?(?:(?:origin|upstream)/)?"
    r"(?:main|master|trunk|develop|head|[\w./-]*branch)\b",
    re.IGNORECASE,
)
_SHA_TOKEN_RX = _lazy_re(_SHA_RX)

# Negation / deferral / referential cues. If any appears in the window AROUND a claimed SHA, the
# "claim" is actually a denial, a deferral, or a reference to a SHA the USER supplied — NOT a
# fabricated commit assertion. We look back further than forward because the negation usually
# precedes: "have NOT committed ... a1b2c3d".
_NEG_REF_RX = _lazy_re(
    r"""
      \bnot\s+(?:yet\s+)?commit             # "not commit", "not committed", "not yet committ..."
    | \bnot\s+(?:yet\s+)?tagg               # "not tagged"
    | \bn['’]t\s+(?:yet\s+)?commit          # "haven't committed", "didn't commit"
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
_CLAUSE_BOUNDARY_RX = _lazy_re(
    r"[.;\n]|\bbut\b|\bhowever\b|\bthough\b|\bwhereas\b", re.IGNORECASE
)

# GLOBAL first-person DENIAL of committing/tagging/pushing anywhere in the turn. When the AI
# explicitly says it did NOT commit/tag/push this session, EVERY SHA in the turn is referential
# -> suppress all claims. First-person only: it must be the AI denying ITS OWN action.
_GLOBAL_DENIAL_RX = _lazy_re(
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
_GIT_COMMIT_OR_TAG_RX = _lazy_re(
    r"\bgit(?:" + _GIT_OPT + _GIT_OPT_VAL + r")*\s+(commit|tag)\b([^;&|\n]*)"
)
# Only an invocation that CREATES an object grounds a SHA. git's own grammar: `commit --dry-run`
# creates nothing; `tag` creates only when it names a tag and is in none of its read modes (list,
# delete, verify, and the filters that imply list). A read-only `git tag -l` grounds nothing.
_TAG_READ_MODE_RX = _lazy_re(
    r"(?:^|\s)(?:-[a-zA-Z]*[ldv][a-zA-Z]*|-n\d*|--(?:list|delete|verify|contains|no-contains"
    r"|points-at|merged|no-merged|column|sort|format)\b)"
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

    Two-stage: (1) the SHA's clause must place it in git history (`_HISTORY_CUE_RX`);
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
    starts = [0] + [c.end() for c in _CLAUSE_RX.finditer(text)]
    ends = [c.start() for c in _CLAUSE_RX.finditer(text)] + [len(text)]
    for c0, c1 in zip(starts, ends):
        clause = text[c0:c1]
        if not _HISTORY_CUE_RX.search(clause):
            continue
        for m in _SHA_TOKEN_RX.finditer(clause):
            sha = m.group(1).lower()
            if sha in seen:
                continue
            s, e = c0 + m.start(1), c0 + m.end(1)
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
    """True iff any prior Bash tool_use actually ran a `git commit` / `git tag` that creates.

    Form-agnostic: matches the bare `git commit`, a cd'd-directory commit, and every
    `git <global-options...> commit|tag` form. See _GIT_COMMIT_OR_TAG_RX. Both Pre/PostToolUse
    rows pass through (either proves the commit invocation happened).
    """
    for tool, cmd, _resp in iter_tool_events(history):
        if tool != "Bash" or not isinstance(cmd, str) or not cmd:
            continue
        for m in _GIT_COMMIT_OR_TAG_RX.finditer(_QUOTED_RX.sub(" ", cmd)):
            verb, rest = m.group(1), m.group(2)
            if verb == "commit" and "--dry-run" not in rest:
                return True
            if verb == "tag" and not _TAG_READ_MODE_RX.search(rest) \
                    and any(not w.startswith("-") for w in rest.split()):
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

sha_CHECK = Check(id='content.fabricated_commit_sha', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('committed', 'Committed', 'commit', 'Commit', 'tagged', 'Tagged', 'tag', 'Tag', 'landed', 'Landed', 'pushed', 'Pushed', 'merged', 'Merged', 'created', 'Created', 'made', 'Made', 'shipped', 'Shipped', 'main', 'master', 'trunk', 'develop', 'HEAD', 'head', 'branch'), retry_hint=sha_RETRY_HINT, description=sha_DESCRIPTION, eats=frozenset({"current_event", "history", "pattern"}), tests="LINEAGE")
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
_INTERRUPTION_CLAIM_RX = _lazy_re(
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
# content.unsourced_webfetch — a fetched URL not in any prior tool_result.
#
# The agent invents a URL, often from a plausible-looking host+path pattern in training data,
# never returned by a prior search or supplied by the user.
#
# Predicate walks session history and checks whether the URL appears anywhere in prior
# tool_response content, or -- the one that keeps the condition honest -- was typed verbatim by
# the USER in a genuine transcript turn. The fetch is the effect, not the tool: WebFetch, an MCP
# fetch tool, or a url client in Bash (round nine H1). No host is trusted: a known host does not
# witness an invented path under it. "Not in a prior tool_result" is a proxy for "fabricated", and it
# is a proxy that misfires on the single most clearly-grounded case there is; see `_user_supplied`
# for the measured misfire.
import json
import os
from makoto.kit import raw_payload_str, unwitnessed
from makoto.vocab import Finding


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


# Programs whose url arguments are retrieved when the command runs. A url handed to one of these
# is a fetch whatever tool carries it: `curl <url>` in Bash is the same unseen resource as the
# same url in WebFetch.
_URL_CLIENTS = frozenset({"curl", "wget", "http", "https", "xh", "aria2c", "lynx", "w3m",
                          "links", "fetch"})
_URL_RX = _lazy_re(r"https?://[^\s'\"<>]+")


def _fetched_urls(current_event: dict) -> tuple:
    """Every url a PreToolUse event is about to retrieve: the `url` input of WebFetch or of an
    MCP tool whose name says it fetches, and each url argument to a url client in a Bash command.

    No host vouches for a url: a well-known host says nothing about whether the PATH exists, and
    an invented `github.com/<org>/<repo>/blob/...` is exactly as unseen as any other invented
    page. Only a prior tool response or the user's own turn witnesses a url."""
    if current_event.get("hook_event_name") != "PreToolUse":
        return ()
    name = current_event.get("tool_name") or ""
    tool_input = current_event.get("tool_input") or {}
    url = tool_input.get("url")
    if name == "WebFetch" or (name.startswith("mcp__") and "fetch" in name.lower()):
        return (url,) if isinstance(url, str) and url else ()
    if name != "Bash":
        return ()
    from makoto.core._shell import _shell_segments
    out = []
    for argv, _ in _shell_segments(tool_input.get("command") or ""):
        if argv and os.path.basename(argv[0]) in _URL_CLIENTS:
            out += [m.group(0) for a in argv[1:] for m in _URL_RX.finditer(a)]
    return tuple(dict.fromkeys(out))


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
    """OTHER_POINT: a fetch commits to each url it retrieves."""
    return _fetched_urls(ev)


def webfetch_predicate(*, current_event: dict, history: list, pattern, conn=None) -> Optional[Finding]:
    """The Pre predicate. Fires iff a url the event fetches (`_fetched_urls`) is witnessed by neither a prior tool RESPONSE (`_url_grounded_in_history`)
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
# gate.unread_structure -- a traversal of structured data produced `null`, and nothing in this
# session had looked at the structure first: the positions were assumed to line up rather than
# read. At the act grain, a `jq` or `python -c` that reads a structured file and prints `null` is
# the pairing failing IN THIS SESSION, on the record makoto already holds -- the command and what
# it printed.
#
# `null` IS THE SIGNAL, and nothing narrower. A traversal that prints a wrong non-null value is
# invisible here (it needs the intended value, which is not on any channel makoto reads) and a
# traversal that prints nothing at all is excluded deliberately: an empty stdout is what a great
# many correct commands produce. Only a literal JSON `null` as the whole of what was printed
# counts. That is a named RECALL bound, and it fails quiet.
#
# ONLY THE LATEST TRAVERSAL COUNTS (BLOCK since 2026-09-25): it owes iff it printed null and no
# structure read precedes it. The discharge is in-turn -- read the structure, then re-run the
# traversal -- so an early null that was since read around no longer holds every later stop.
from makoto.kit import response_text, command_of, decode_history_event, unwitnessed

# A structured-data traversal. `jq` is the canonical one; `python -c ... json` and `yq` are the
# same act under other programs. A closed vocabulary whose miss is a RECALL bound.
_TRAVERSAL_RX = _lazy_re(r"\b(?:jq|yq|json_pp)\b|python3?\s+-c\b[^\n]*\bjson\b")
# The structure query that pays the obligation: any of the shape-printing jq forms, or a Read of
# the file.
_STRUCTURE_RX = _lazy_re(r"\b(?:jq|yq)\b[^\n]*(?:\bkeys\b|\btype\b|\bhas\s*\(|\blength\b|"
                           r"\bpaths\b|\bto_entries\b|-e\b)")
# What a failed traversal prints: a literal null as the WHOLE output -- JSON's `null` (jq/yq) or
# Python's `None` (the same absent-value token printed by a `python3 -c ...json...` traversal).
# `.strip()` has already run, so an anchored match is the whole of it.
_NULL_OUTPUT_RX = _lazy_re(r"\A(?:null|None)\Z")


def _is_traversal(ev: dict) -> bool:
    cmd = command_of(ev)
    return ev.get("hook_event_name") == "PostToolUse" and bool(cmd and _TRAVERSAL_RX.search(cmd))


def _is_structure_read(ev: dict) -> bool:
    if ev.get("tool_name") == "Read":
        return True
    cmd = command_of(ev)
    return bool(cmd and _STRUCTURE_RX.search(cmd))


def unread_structure_gate(history) -> Optional[Finding]:
    """Fire iff the session's latest traversal printed null and no structure read precedes it."""
    events = [ev for ev in map(decode_history_event, history or ()) if isinstance(ev, dict)]
    last = max((i for i, ev in enumerate(events) if _is_traversal(ev)), default=None)
    if last is None or not _NULL_OUTPUT_RX.match(response_text(events[last])):
        return None
    end = len(events)
    for _it, _at in unwitnessed(
            list(enumerate(events)) + [(end, None)],
            owes=lambda it: (last,) if it[0] == end else (),
            pays=lambda it: (lambda at, i=it[0]: i < at)
            if it[1] is not None and _is_structure_read(it[1]) else None):
        return Finding(
            pattern_id="gate.unread_structure", file="", line=0, level="error",
            message=("A traversal of structured data printed `null` and nothing in this session "
                     "looked at the structure first — the positions were assumed to line up "
                     "rather than read."),
            retry_hint=("Print a non-null datum from the file first (`jq 'keys'`, `jq 'type'`, "
                        "`jq -e 'has(...)'`) or Read it, then re-run the traversal."),
            snippet=command_of(events[last])[:200])
    return None


structure_CHECK = _Check(id="gate.unread_structure", applies_at="Stop", posture="BLOCK",
               tests="LINEAGE",
               eats=frozenset({"history"}),
               run=lambda c: unread_structure_gate(c.history))

# ==============================================================================================
# unknownRefSwitch
# ==============================================================================================
# gate.unknown_ref_switch -- HEAD was moved to a ref nothing in this session had printed.
# Switching a ref is a boundary, and what must survive it (the work in the tree) has to be named
# before the boundary is crossed: a `git checkout` or `git switch` in the session's own Bash
# record is a boundary crossed in front of makoto, and whether the ref was ever printed first is
# two commands on the record.
#
# PRE-EDGE DENY (2026-09-25): the switch is refused before HEAD moves; the discharge is to print
# the refs (`git branch`, `git rev-parse --verify <ref>`) and retry.
from makoto.kit import unmet_obligation_gate, command_matches
from makoto.core._shell import _basename, _effective_argv, _git_subcommand, _shell_segments

# Moving HEAD. `git checkout <ref>` and `git switch <ref>` are the two forms, read per shell
# segment (`core._shell`), so `git -C dir checkout`, doubled spaces and `a || b` chains parse as
# git does. `git checkout -- <path>` restores a FILE and moves nothing: a leading `--` is no
# switch. `git reset --hard <ref>` moves HEAD (and the working tree) to a ref the same way;
# `git reset --hard` with no ref discards edits in place and names no boundary to cross.
#
# CREATING A BRANCH NAMES THE NEW REF ITSELF: `checkout -b|-B|--orphan NEW [BASE]` and
# `switch -c|-C|--create|--force-create|--orphan NEW [BASE]` make NEW, so NEW is not an unknown
# ref, and a later segment of the same command switching to NEW (the create-or-switch idiom
# `git checkout -b X || git checkout X`) is not either. Only BASE, when given, is held to the
# rule. A BASE of `HEAD` or `@` moves nothing.
_CREATE_FLAGS = frozenset({"-b", "-B", "-c", "-C", "--orphan", "--create", "--force-create"})
_STAY_REFS = frozenset({"HEAD", "@"})
# A redirection word shlex leaves in the argv (`2>/dev/null`, `>`, `&>log`): never a ref.
_REDIRECT_RX = _lazy_re(r"\d*&?[<>]+&?")
# Printing the ref. `git status` and `git log` are NOT here, because neither names the ref being
# switched TO.
_REF_PRINT_RX = _lazy_re(r"\bgit\s+(?:rev-parse|branch|show-ref|for-each-ref|ls-remote)\b")


def _without_redirects(args):
    """`args` minus redirections: shlex splits `2>/dev/null` into `2`, `>`, `/dev/null`, and
    none of the three is a ref."""
    out = []
    for a in args:
        if out and out[-1] is None:
            out[-1:] = []            # the redirect's target word
            continue
        if _REDIRECT_RX.match(a):
            if out and out[-1].isdigit():
                out.pop()            # the fd number glued in front of it
            if _REDIRECT_RX.fullmatch(a):
                out.append(None)     # its target is the next word
            continue
        out.append(a)
    return [a for a in out if a is not None]


def _switch_target(argv, created: set):
    """The ref this git segment moves HEAD to, or None; records any branch it creates."""
    eff = _effective_argv(argv)
    if not eff or _basename(eff[0]) != "git":
        return None
    sub, args = _git_subcommand(eff)
    if sub == "reset":
        if "--hard" not in args:
            return None
        rest = [a for a in args if not a.startswith("-")]
        return rest[0] if rest else None
    if sub not in ("checkout", "switch"):
        return None
    positional, made = [], None
    it = iter(_without_redirects(args))
    for a in it:
        if a == "--":
            break
        if a in _CREATE_FLAGS:
            made = next(it, None)
        elif not a.startswith("-"):
            positional.append(a)
    if made is not None:
        created.add(made)
        base = positional[0] if positional else None
        return None if base is None or base in _STAY_REFS else base
    if not positional or positional[0] in created or positional[0] in _STAY_REFS:
        return None
    return positional[0]


def _is_ref_switch(ev: dict) -> bool:
    cmd = command_of(ev)
    if not cmd:
        return False
    created: set = set()
    return any(_switch_target(argv, created) is not None for argv, _op in _shell_segments(cmd))


# `kit.command_matches` is the one body for "this event's command matches a regex" -- four
# copies of it appeared the moment this batch landed and the duplicate-function law caught them.
_is_ref_print = command_matches(_REF_PRINT_RX)


unknown_ref_switch_gate = unmet_obligation_gate(
    act=_is_ref_switch,
    guard=_is_ref_print,
    message=("HEAD is about to move to a ref that nothing in this session had printed — switching a ref "
             "is a boundary, and what has to survive it was never named."),
    retry_hint=("Print the refs first (`git rev-parse --verify <ref>`, `git branch`, "
                "`git show-ref`) so the switch is to something known."),
)


ref_RETRY_HINT = "Print the refs first, then retry the switch."
ref_DESCRIPTION = "HEAD moved to a ref nothing in this session printed"
ref_CHECK = _Check(id="gate.unknown_ref_switch", applies_at="Pre", posture="BLOCK",
               predicate_module=__name__, keywords=("checkout", "switch", "reset"),
               retry_hint=ref_RETRY_HINT,
               description=ref_DESCRIPTION,
               tests="LINEAGE",
               eats=frozenset({"current_event", "history", "pattern", "conn"}))

# ==============================================================================================
# unprobedFanout
# ==============================================================================================
# gate.unprobed_fanout -- work was dispatched to a subagent and nothing in this session had read,
# globbed or grepped first, so the brief was written from assumption: a baseline read of the
# ground before work is dispatched onto it, entirely on the record makoto already reads (a
# Task/Agent event, and a Read/Glob/Grep event before it).
#
# PRE-EDGE DENY (2026-09-25): the dispatch is refused before it launches; the discharge is one
# Read, Glob or Grep of the ground, then retry. The guard is read from the whole session, not the
# 1-hour window (`kit._session_rows`): Reads older than the window used to go unseen.
from makoto.kit import unmet_obligation_gate, _session_rows
from makoto.core._shell import _basename, _effective_argv, _shell_segments

# The dispatch tools. `Task` is the documented subagent tool name; `Agent` is the same act under
# the name this harness reports, and both are accepted by name alone. An MCP tool that dispatches
# a subagent under a third name (`mcp__subagents__dispatch`) is the same act, recognized by its
# `prompt` input rather than guessed by name -- the brief a dispatch hands off is the one input
# common to every dispatch tool, named or not.
_DISPATCH_TOOLS = frozenset({"Task", "Agent"})
# The reads that pay the obligation.
_PROBE_TOOLS = frozenset({"Read", "Glob", "Grep"})
# The same read under Bash: a segment whose command position runs one of these read-only readers
# (`sed -n 1,80p f.py`, `grep -n x f.py`, `cat f`) looked at the ground exactly as Read/Grep would.
# `sed` counts only under `-n` (its `-i` edits in place) and `find` only without an action that
# writes or runs something (`-delete`, `-exec*`, `-ok*`, `-fprint*`). A closed vocabulary whose
# miss is a RECALL bound: the gate still fires on a reader it does not name.
_BASH_READERS = frozenset({"cat", "head", "tail", "grep", "egrep", "fgrep", "rg", "ls", "wc"})
_FIND_WRITING_ACTIONS = ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fls")


def _is_dispatch(ev: dict) -> bool:
    name = ev.get("tool_name") or ""
    if name in _DISPATCH_TOOLS:
        return True
    if not name.startswith("mcp__"):
        return False
    lname = name.lower()
    if "agent" not in lname and "dispatch" not in lname:
        return False
    return isinstance((ev.get("tool_input") or {}).get("prompt"), str)


def _is_reader_argv(argv) -> bool:
    eff = _effective_argv(argv)
    if not eff:
        return False
    prog, args = _basename(eff[0]), eff[1:]
    if prog in _BASH_READERS:
        return True
    if prog == "sed":
        return "-n" in args and not any(a.startswith(("-i", "--in-place")) for a in args)
    if prog == "find":
        return not any(a.startswith(_FIND_WRITING_ACTIONS) for a in args)
    return False


def _is_probe(ev: dict) -> bool:
    if ev.get("tool_name") in _PROBE_TOOLS:
        return True
    cmd = command_of(ev) if ev.get("tool_name") == "Bash" else ""
    return bool(cmd) and any(_is_reader_argv(argv) for argv, _op in _shell_segments(cmd))


_fanout_obligation = unmet_obligation_gate(
    act=_is_dispatch,
    guard=_is_probe,
    message=("Work is being dispatched to a subagent and no Read, Glob or Grep appears earlier in "
             "this session's recorded events — the brief was written from assumption, and work "
             "built on an assumed baseline is inherited whole. A session that holds no Read, "
             "Glob, Grep or Bash tool retries the same dispatch: the deny fires once."),
    retry_hint=("Read, glob or grep the ground before dispatching, so the brief describes what "
                "is there; or confirm the dispatch was itself the exploration."),
)


def unprobed_fanout_gate(*, current_event: dict, history: list, pattern, conn=None):
    """The deny fires once per unprobed stretch. A session with no reading tool cannot pay it
    (measured 2026-09-28: a coordinator session holding only messaging tools was denied every
    dispatch, twice, with no exit), and Gabriel's rule of 01:16Z forbids a precaution with no
    exit. So an earlier dispatch attempt at the Pre edge, with no probe after it, means the deny
    was already shown: this retry goes through."""
    finding = _fanout_obligation(current_event=current_event, history=history, pattern=pattern, conn=conn)
    if finding is None:
        return None
    events = [ev for ev in map(decode_history_event, _session_rows(
        conn, current_event.get("session_id", ""), history)) if isinstance(ev, dict)]
    if events and events[-1] == current_event:
        events.pop()        # the store already holds this call itself: it is not an earlier try
    shown = False
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("hook_event_name") == "PreToolUse" and _is_dispatch(ev):
            shown = True
        elif ev.get("hook_event_name") in ("PostToolUse", "PostToolUseFailure") and _is_probe(ev):
            shown = False
    return None if shown else finding


fanout_RETRY_HINT = "Read, glob or grep the ground, then retry the dispatch."
fanout_DESCRIPTION = "a subagent dispatch with no Read, Glob or Grep earlier in the session"
fanout_CHECK = _Check(id="gate.unprobed_fanout", applies_at="Pre", posture="BLOCK",
               predicate_module=__name__, keywords=("prompt",),
               retry_hint=fanout_RETRY_HINT,
               description=fanout_DESCRIPTION,
               tests="LINEAGE",
               eats=frozenset({"current_event", "history", "pattern", "conn"}))
# gate.pasted_fix -- the same repair landed at a second site with nothing run in between, so the
# second site's correctness was INFERRED from the first rather than checked.
#
# THE NAIVE READING IS INDISCRIMINATE. Read as "two or more edits with no verifier run between
# them", the rule fires on 136 of this tree's own 185 non-merge commits -- 73.5%, simply what
# writing code looks like.
#
# WHAT THE RECORD CAN DECIDE, and the three narrowings, each with the rate it bought over those
# same 185 commits. A commit stands in for one session's introduced text: it over-counts in one
# direction (a session may span commits) and under-counts in the other, but it is real text
# introduced by real sessions on this tree, and it is the only such record there is.
#
#   1. THE SAME TEXT, not merely two edits -- a normalized block reaching two DISTINCT files.
#                                                                         73.5% -> 9.2%
#   2. A CHANGE TO WHAT EXISTS -- `Edit`/`MultiEdit` only. A fix is edited into a file that is
#      already there, while a file being WRITTEN carries the house import header; admitting
#      written files is what puts `from __future__ import annotations` in front of the gate.
#                                                                          9.2% -> 3.8%
#   3. SUBSTANCE -- the block must carry a line that is not a comment, an import or a decorator.
#      A comment quoted at two sites is prose with one home, not a repair whose correctness was
#      inferred.                                                          3.8% -> 3.2%
#
# THE GRAIN IS FOUR SUBSTANTIAL LINES, a measurement rather than a preference: at one line the
# reading fires on 21.1% of commits (the house predicate header and every parallel call site); at
# eight it fires on nothing. At four, most of the fires are the fault.
#
# NAMED RECALL BOUND: a repair SHORTER than four substantial lines is not a finding -- on this
# tree's own record a one-line repeat is indistinguishable from convention (21.1% against 3.2%).
# The bound fails QUIET, the direction an advisory gate should fail.
#
# THE DISCHARGE: a verifier run after the FIRST landing pays -- between the two landings, or after
# the second, since that run checks the second site too (2026-09-25; before, only a run between
# them paid, so nothing in-turn could discharge a fire). A run before the first does not. That is why this gate
# is NOT written on `kit.unmet_obligation_gate`, whose guard, once seen, pays for the rest of the
# session. The vocabulary of "a verifier ran" is `kit.ran_a_verifier`, unchanged and unwidened.
#
# DISCRIMINANT AGAINST `gate.unwitnessed_verifier`: that gate reads the verifier's REPORT and asks
# whether this session has ever seen it print a failure, so one clean run with no red anywhere
# fires it while this gate has no mutation to look at at all. This one reads MUTATIONS and asks
# only WHERE a run falls between two of them; the report is never consulted, so a session that
# runs a RED verifier between two identical pastes is silent here and loud there.
#
# `event.thrash_revert` is the nearest prose neighbour and the two are never paired: it is a
# Pre-tier check on a different edge, asking whether a file is being written back to a value it
# already held -- one file returning to a prior state, against one text reaching a second file.
#
# BLOCK TIER: the discharge is one verifier run, in-turn.
from makoto.kit import decode_history_event, introduced_text, ran_a_verifier, unwitnessed

# A fix is a change to what already EXISTS. See narrowing 2 above for the rate this buys.
_EDIT_TOOLS = frozenset({"Edit", "MultiEdit"})
# How many contiguous substantial lines make a block. Measured; see above. Not a tunable
# threshold but the point where the reading stops naming convention and has not yet stopped
# naming anything.
_BLOCK_LINES = 4
# A line carrying no content of its own: closers, separators, a bare marker.
_TRIVIAL_RX = _lazy_re(r"^[\s)\]},:;#\"']*$")
# A line that travels as CONVENTION rather than as a repair: a comment, an import, a decorator,
# a docstring fence, a markup tag.
_CONVENTION_RX = _lazy_re(r"^(#|//|import\s|from\s+\S+\s+import\s|@|\"\"\"|'''|<)")


def _kept_lines(text: str) -> list:
    """`text`'s lines, whitespace-normalized, with the ones carrying nothing dropped.

    THE NORMALIZATION IS LOAD-BEARING: the margin goes and internal runs of whitespace collapse,
    so a paste that was REINDENTED at its second site is still the same paste. Without it, a fix
    moved into a deeper block reads as new text and the gate goes quiet on it.
    """
    out = []
    for line in (text or "").splitlines():
        flat = " ".join(line.split())
        if flat and not _TRIVIAL_RX.match(flat):
            out.append(flat)
    return out


def _blocks(lines: list) -> list:
    """Every contiguous run of `_BLOCK_LINES` kept lines that carries at least one substantial
    line -- see narrowing 3. A window of nothing but imports, comments and decorators is
    convention travelling, and convention travels legitimately.

    Each line's substance is decided ONCE, on its own, and the windows then slide a running
    count over those decisions rather than an `any(...)` re-reading every line of every window
    (which re-tested each line `_BLOCK_LINES` times); this is O(n) and says per line what it
    decided.
    """
    carries = [0 if _CONVENTION_RX.match(line) else 1 for line in lines]
    out = []
    substance = sum(carries[:_BLOCK_LINES])
    for i in range(len(lines) - _BLOCK_LINES + 1):
        if i:
            substance += carries[i + _BLOCK_LINES - 1] - carries[i - 1]
        if substance:
            out.append("\n".join(lines[i:i + _BLOCK_LINES]))
    return out


def _second_site_finding(block: str, first_file: str, second_file: str) -> Finding:
    head = block.split("\n")[0]
    return Finding(
        pattern_id="gate.pasted_fix",
        file=second_file,
        line=0,
        level="error",
        message=(
            f"The same change reached `{second_file}` after `{first_file}` with no verifier run "
            f"between the two landings, starting `{head}` — so the second site's correctness is "
            f"drawn from the first rather than checked."
        ),
        retry_hint=(
            "Run the verifier between the two landings, or order the change by dependence and "
            "make one per pass. A repair that transfers is a claim about the second site, and "
            "the first site's green is not evidence for it."
        ),
        snippet=head[:200],
    )


def pasted_fix_gate(history) -> Optional[Finding]:
    """Fire iff one block of introduced text reached a SECOND file with no verifier run between
    the two landings. LINEAGE: the second landing owes a witness -- a verifier run after the first
    landing -- and only a run at or after that point pays it."""
    landed = {}

    def owes(item):
        at, ev = item
        tool = ev.get("tool_name", "")
        tool_input = ev.get("tool_input")
        # A block LANDS (registers as a possible first site) from a Write same as an Edit --
        # narrowing 2 is about which site TRIGGERS a fire, not which site is remembered. Without
        # this, a fix Written into a brand-new module and then Edited into a second file is
        # invisible: the Write never enters `landed`, so the Edit is never seen as a second paste.
        if ev.get("hook_event_name") != "PostToolUse" or tool not in (_EDIT_TOOLS | {"Write"}) \
                or not isinstance(tool_input, dict):
            return ()
        path = str(tool_input.get("file_path", ""))
        second = []
        for block in _blocks(_kept_lines(introduced_text(tool, tool_input))):
            where, first = landed.setdefault(block, (path, at))
            # Only an Edit/MultiEdit second landing fires (narrowing 2): two Writes sharing a
            # block is convention (e.g. a house import header), never a repair transfer.
            if where != path and tool in _EDIT_TOOLS:
                second.append((block, where, first, path))
        return second

    def pays(item):
        at, ev = item
        return (lambda subject: subject[2] < at) if ran_a_verifier(ev) else None

    events = [ev for ev in map(decode_history_event, history or ()) if isinstance(ev, dict)]
    # Every second landing is owed at the END of the record, so a run after it can still pay.
    pending = [s for it in enumerate(events) for s in owes(it)]
    end = (len(events), {})
    for _ev, (block, where, _first, path) in unwitnessed(
            list(enumerate(events)) + [end], owes=lambda it: pending if it is end else (),
            pays=pays):
        return _second_site_finding(block, where, path)
    return None


pasted_CHECK = _Check(id="gate.pasted_fix", applies_at="Stop", posture="BLOCK",
               tests="LINEAGE",
               eats=frozenset({"history"}),
               run=lambda c: pasted_fix_gate(c.history))
# gate.unclaimed_unit -- the session added a unit that answers to nothing: a function nobody
# asked for and nothing reaches is not neutral, it is surface every later reader has to
# understand, every later change has to keep working, and no requirement protects.
#
# WHAT COUNTS AS A CLAIM, and all three are on the record makoto already reads:
#
#   1. THE OPERATOR NAMED IT -- the unit's name appears in a genuine operator turn
#      (`ledger.user_turn_texts`, host-written turns only).
#   2. SOMETHING REACHES IT -- the name appears somewhere in this session's introduced text other
#      than its own definition: a call, an export, a test, an edited call site -- or in the file
#      the unit landed in, read off disk (a registration by name the Edit never carried).
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
# decorate it) or delete it.
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
    on_disk: dict = {}
    unclaimed = [subject for _ev, subject in unwitnessed(
        events, owes=unclaimed_owes,
        paid=(lambda s: sum(1 for tok in _TOKEN_RX.findall(blob or "") if tok == s[0])
                        >= _REACHED_AT,
              lambda s: _reached_in_file(s[0], s[1], on_disk),
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
_TOKEN_RX = _lazy_re(r"[A-Za-z0-9_]+")


# The largest file whose text is read for a use. Past it the witness is simply absent, so the
# gate stays on the introduced text alone.
_FILE_READ_CAP = 2_000_000


def _reached_in_file(name: str, path: str, cache: dict) -> bool:
    """True iff the file the unit landed in names it at least `_REACHED_AT` times: an Edit that
    adds `def f` to a file already registering `f` by name (`_PREDICATES = {X.id: f}`) carries the
    definition but not the use, which is on disk. An unreadable file is no evidence."""
    if not path:
        return False
    if path not in cache:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                cache[path] = _TOKEN_RX.findall(fh.read(_FILE_READ_CAP))
        except OSError:
            cache[path] = []
    return sum(1 for tok in cache[path] if tok == name) >= _REACHED_AT


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
_ROWS = (sha_CHECK, interrupt_CHECK, webfetch_CHECK, structure_CHECK, ref_CHECK, fanout_CHECK, pasted_CHECK, unclaimed_CHECK, unbriefed_CHECK,)
ROWS = {c.id: c for c in _ROWS}
CHECK, *EXTRA_CHECKS = _ROWS
_PREDICATES = {sha_CHECK.id: sha_predicate, interrupt_CHECK.id: interrupt_predicate, webfetch_CHECK.id: webfetch_predicate, unbriefed_CHECK.id: unbriefed_predicate, ref_CHECK.id: unknown_ref_switch_gate, fanout_CHECK.id: unprobed_fanout_gate}


def predicate(*, current_event: dict, history: list, pattern, conn=None):
    """Dispatch calls one predicate per module; this shape's answers for the row it names."""
    return _PREDICATES[pattern.id](current_event=current_event, history=history, pattern=pattern, conn=conn)
