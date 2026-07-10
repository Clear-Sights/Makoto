"""L0 lexicons — the single home for makoto's regexes + word-sets.

Pure data: compiled regexes + frozensets, no in-package imports (L0 of the layered DAG).
Detectors, gates, and primitives import these by name so one edit governs every surface.
Stdlib only (re). CUT verbatim from predicates/helpers.py (Task 3) — never retyped.
"""
from __future__ import annotations
import re


_DONE_WORDS_RX = re.compile(r"\b(done|complete|completed|finished)\b", re.IGNORECASE)

_NEGATION_RX = re.compile(r"\b(not|never|no)\b|n['’]t\b", re.IGNORECASE)

# Universal exemption marker (2026-05-29). Makoto's bundled CLAUDE.md (written by the
# installer) teaches the AI: when a flagged shape is LEGITIMATE, annotate it with
# `makoto-allow: <reason>` and makoto will not flag it. This makes every content-scan
# pattern FP-exemptable EVERYWHERE — a compliant AI marks its legitimate cases, so only
# UNMARKED (likely-violation) content fires. Generalizes the ADR-backlink exemption
# (1.4/1.8) to all content-scan patterns. makoto targets the AI (which reads the bundled
# CLAUDE.md), never the user. The marker is plain-text + case-insensitive so it works in
# any language/comment style. Like the ADR exemption, it is file-level (a deliberate evader
# who writes a false `makoto-allow: <reason>` leaves an on-the-record, auditable rationale).
# Structured marker (2026-06-01, §7.5b): `makoto-allow:` followed by a non-empty reason. A bare
# `makoto-allow` with no colon/reason no longer exempts — an exemption without an on-the-record
# rationale is a reasonless laundering token, which is itself an empty word.
_MAKOTO_ALLOW_RX = re.compile(r"makoto-allow\s*:\s*\S", re.IGNORECASE)
# Reason CAPTURE (the audit half): the rationale text after the colon, for the on-the-record
# exemption row. Same trigger as _MAKOTO_ALLOW_RX (colon + a non-empty reason) — kept separate so
# the hot boolean check stays a bare search and only the recording path pays for the capture.
_MAKOTO_ALLOW_REASON_RX = re.compile(r"makoto-allow\s*:\s*(\S.*)", re.IGNORECASE)

# JWT/JOSE library callee gate — a `decode` call is a JWT verification iff its callee chain names a
# jwt/jose library, BOUNDARY-delimited so `myjwthelper` does not match: `jwt`, `jose` (python-jose),
# `pyjwt`. Shared by content.jwt_signature_disabled (verify=False / verify_signature) and content.jwt_none_alg (algorithms=["none"]).
JWT_CALLEE_RX = re.compile(r"(?i)(?:^|\.)(?:jwt|jose|pyjwt)(?:\.|$)")

# ---- Test-runner provenance + failure-verdict (shared by the ledger + the green-claim gate) ----
# Two shared signals for gate.green_claim (gates.green_claim_gate):
#   _TEST_RUNNER_RX  — does a Bash COMMAND invoke a recognized test runner? (read at record time
#                      by ledger.record_update, which then files the output under kind='testrun').
#                      This is the FP firewall: only genuine test-runner output is consulted, so a
#                      `cat old_failure.log` that happens to print "=== 3 failed ===" is NEVER a
#                      testrun row. Open-world by nature — an unlisted runner is a documented RECALL
#                      bound (the gate stays silent), never a false block.
#   is_failing_testrun — does test-runner OUTPUT show >=1 REAL failure? xfail-safe by
#                      construction: `\bfailed\b` cannot match inside `xfailed`/`xpassed` (no word
#                      boundary), and the count must be >=1, so `=== 681 passed, 3 xfailed ===` and
#                      a clean `=== 681 passed ===` are both NOT failures.
_TEST_RUNNER_RX = re.compile(
    r"\b("
    r"pytest|py\.test|python[0-9.]*\s+-m\s+(?:pytest|unittest)|-m\s+unittest|"
    r"nox|tox|"
    r"jest|vitest|mocha|ava|jasmine|"
    r"go\s+test|cargo\s+(?:test|nextest)|"
    r"npm\s+(?:run\s+)?test|yarn\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|"
    r"rspec|phpunit|ctest|gradlew?\s+test|mvn\s+test|"
    r"make\s+test|just\s+test|rails\s+test|"
    r"scripts/falsify|scripts/cert|scripts/connectivity|measure_corpus_fp"
    r")\b",
    re.IGNORECASE)

# A SUMMARY/count denoting >=1 real failure or error (case-insensitive: pytest/jest print these
# lowercase). xfail/xpassed are excluded by the word boundary; "0 failed" by requiring [1-9]\d*.
_FAILURE_SUMMARY_RX = re.compile(
    r"\b[1-9]\d*\s+failed\b"                      # pytest/jest: 'N failed' (N>=1), xfail-safe
    r"|\b[1-9]\d*\s+errors?\b"                    # pytest: 'N errors'
    r"|Traceback \(most recent call last\):",     # an uncaught exception tail
    re.IGNORECASE)

# Per-test / per-package FAILURE markers — case-SENSITIVE (uppercase runner markers only), so prose
# like "failed to connect" never matches. Anchored at line start.
_FAILURE_MARKER_RX = re.compile(
    r"^(?:FAILED\s+\S|ERROR\s+\S|FAIL\b|={2,}\s*FAILURES\s*={2,}|={2,}\s*ERRORS\s*={2,})",
    re.MULTILINE)

# ANSI SGR color codes. vitest/jest colorize the summary, and the SGR terminator 'm' is a WORD char
# that abuts the count ('\x1b[31m2 failed'), killing the \b before `[1-9]\d* failed` so a REAL
# failing run reads as green. Stripped before failure detection (is_failing_testrun) — FP-safe:
# removing color cannot manufacture a failure, and the count/xfail word-boundary guards are untouched.
_ANSI_SGR_RX = re.compile(r"\x1b\[[0-9;]*m")

# _ADMIT_CORE — the retrospective first-person admission shapes.
_ADMIT_CORE_RX = re.compile(
    r"\bI\s+(?:didn['’]t|did\s+not)\s+(?:actually\s+)?"
    r"(?:finish|complete|run|verify|test|check|implement|do)\b"          # hollow prior claim
    r"|\bI\s+forgot\b"                                                    # omitted prior work (gated by _ASIDE)
    r"|\bI\s+missed\b"                                                    # overlooked prior work
    r"|\bI\s+overclaimed\b"
    r"|\bI\s+was\s+wrong\b"
    r"|\bI\s+should\s+have\b"
    r"|\b(?:it|that|this)\s+(?:isn['’]t|wasn['’]t|is\s+not|was\s+not)\s+actually\s+done\b",
    re.IGNORECASE,
)

# _FORWARD — a future frame voids the match: "I didn't run it YET, I WILL run it next"
# describes work ahead, not a hollow prior claim. Requires both a `yet` token AND a future
# verb in the admission's clause window.
_FORWARD_YET_RX = re.compile(r"\byet\b", re.IGNORECASE)

_FORWARD_FUTURE_RX = re.compile(r"\b(?:will|going\s+to|gonna|next|I['’]ll)\b", re.IGNORECASE)

# _ASIDE — "I forgot to mention/note/add/say/point out ..." is a conversational aside, NOT
# an admission that prior WORK is incomplete. Only the `forgot` core is gated by this.
_ASIDE_RX = re.compile(r"\bI\s+forgot\s+to\s+(?:mention|note|add|say|point\s+out|tell)\b", re.IGNORECASE)

# A nearby user-concession STRENGTHENS (not required). Surfaced for callers that want it.
_USER_CONCESSION_RX = re.compile(
    r"\b(?:you['’]re\s+right|as\s+you\s+said|you\s+caught|you\s+pointed\s+out|"
    r"you\s+were\s+right|good\s+catch)\b",
    re.IGNORECASE,
)

# Wide success/completeness lexicon (fixes the success-synonym gap: done|complete|finished
# missed "full/all/shipped/ideal/optimal/green/verified/merged/...").
_SUCCESS_WORDS_RX = re.compile(
    r"\b(done|complete|completed|finished|fully|full|all|every|everything|exhaustive|"
    r"shipped|merged|deployed|verified|passing|green|ideal|optimal|ready)\b",
    re.IGNORECASE,
)

# The subset that asserts a COMPLETE set (the universal/completeness quantifiers).
_UNIVERSAL_RX = re.compile(
    r"\b(all|every|everything|fully|full|complete|completed|exhaustive|entire|whole|each)\b",
    re.IGNORECASE,
)

# An enumeration of the scope: a count adjacent to a universal ("all 712", "5 of 5"),
# OR a list/count anywhere ("\n- ", "\n1.", "N tests", "N%"). Presence => scope is checkable.
_ENUMERATION_RX = re.compile(
    r"\b\d[\d,]*\s*(of\s+\d|%|tests?|cases?|files?|patterns?|items?|atoms?|factors?|tasks?|steps?|"
    r"passed|passing|failed|failing|xfailed|xpassed|skipped|green|/\s*\d)"
    r"|(?:^|\n|\s)\s*(?:[-*]|\d+[.)])\s",
    re.IGNORECASE,
)

_CITATION_RX = re.compile(
    r'\b([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+(?:et al\.\s+)?(\d{4})\b'
)

# Capitalized English words that match the Author position of the regex but
# aren't author surnames. Added 1.0.5 (v§16): live audit log showed 40% FP rate
# on content.phantom_citation from precisely this shape — 'Saved 2026' (date prefix),
# 'The 2023' (article+year), etc.
_CITATION_AUTHOR_STOPWORDS = frozenset({
    # Articles / determiners
    "The", "This", "That", "These", "Those", "A", "An", "Any", "Some",
    # Prepositions in title case
    "From", "Per", "On", "In", "At", "By", "For", "Of", "To", "With",
    "Without", "About", "Above", "After", "Before", "Between", "During",
    "Through", "Under", "Over", "Across", "Against",
    # Verbs commonly capitalized at sentence start
    "Saved", "Updated", "Created", "Modified", "Added", "Removed", "Deleted",
    "Changed", "Fixed", "Built", "Generated", "Posted", "Published",
    "Started", "Stopped", "Run", "Ran", "Sent", "Received",
    # Pronouns
    "We", "I", "He", "She", "It", "They", "You",
    # Common sentence-starters
    "Here", "There", "When", "Where", "How", "Why", "What", "Who", "Which",
    "Note", "Also", "And", "Or", "But", "Both", "Either", "Neither",
    # Calendar / time
    "Today", "Yesterday", "Tomorrow", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
    # Frequent in dev contexts
    "Version", "Release", "Build", "Phase", "Step", "Task", "Goal",
    "Task", "Item", "Issue", "Section", "Chapter", "Part", "Page",
})


# --- Stop-gate vocabulary (relocated from engine.py, §3b/§6 — L0) ---

# A PRODUCTION claim asserts the assistant PRODUCED/changed a file (past/perfective):
# "wrote / created / added / saved / updated / implemented ... <path>". The completion gate
# fires only when such a verb GOVERNS a located path that has no trace — never on a mere
# co-occurrence of a done-word and a path. This is the 'make it clearer, not looser' fix for
# the measured 9% completion-gate FP (displaying code, listing a subagent's deliverable, an
# incidental path mention). A produce verb within _BIND_BEFORE chars before the path, or
# _BIND_AFTER chars after it (for "<path> was created"), binds — unless a forward frame
# ("will/going to/next/TODO") or a negation ("didn't/couldn't/not") sits right against it.
# A produce verb in ACTIVE past/perfective voice. `built(?!-)` so the adjective "built-in"
# does not false-match. The gate requires the verb to sit BEFORE the path and govern it
# directly — "I created `X`", "Wrote `X` to `Y`" — never the passive "`X` was created" or a
# verb that governs a different clause's noun.
_PRODUCE_VERB_RX = re.compile(
    r"\b(wrote|written|created|added|saved|implemented|generated|produced|built(?!-)|"
    r"updated|modified|landed|committed|emitted|wired|refactored|patched|"
    r"finished|completed)\b", re.IGNORECASE)
# A passive/copular auxiliary right before the verb ⇒ "was written / is wired" — a
# description of state or of another subject's action, NOT a first-person production claim.
_BE_AUX_RX = re.compile(r"(?:\b(?:was|were|is|are|been|being|be|am)\s*$)|(?:['’](?:s|re)\s*$)", re.IGNORECASE)
# A clause boundary between the verb and the path ⇒ the verb governs a different clause.
_CLAUSE_BREAK_RX = re.compile(r"[.;:\n—]")
# A double- or single-quoted string span — used to blank quoted argument bodies before scanning a shell
# command, so a --message/path body that merely MENTIONS a keyword can't masquerade as the command itself.
_QUOTED_RX = re.compile(r'"[^"]*"|\'[^\']*\'')
# A full ```fenced``` code block (DOTALL: the span crosses newlines). L0 SINGLE SOURCE for fenced-span
# extraction — substrate.claims._code_spans (fences + inline backticks) and retraction._fenced_spans both consume
# this exact object, so the fence regex lives in one place. Distinct from commitments._FENCE_RX, a
# line-anchored parity marker (a different algorithm, correctly not shared).
_FENCE_SPAN_RX = re.compile(r"```.*?```", re.DOTALL)

# UNAMBIGUOUS integrity / verification / audit vocabulary (a raw alternation STRING, not a compiled
# PreCheck — each consumer anchors it differently). L0 SINGLE SOURCE for the integrity-named-concept
# word-set: pattern_1_4 (suppression-flag KEY names an integrity concept, anchored into a TOML-line
# regex) and pattern_1_2 (env-gated audit — the gated body / env-var key names an integrity concept)
# both consume THIS string, so the vocabulary lives in one place. Deliberately NARROW: broad stems
# (validat/guard/enforc/seal/complian) were dropped 2026-06-02 after a reviewer cited concrete
# non-integrity toggles they would block (`input_validation_skip` = web-form validation, a UI
# `guard_skip`, a rate-limit `enforce_skip`). Every stem here names the integrity/verification/audit
# of a CHECK, not a generic policy — so a blocking fire stays MATERIAL.
_INTEG_VOCAB = r"audit|verif|integrit|attest|checksum|signatur|tamper|provenance"
_FORWARD_FRAME_RX = re.compile(
    r"\b(will|going to|gonna|i'?ll|plan to|need to|about to|next|todo|should|"
    r"would|hope to|want to|let'?s)\b", re.IGNORECASE)
_NEG_FRAME_RX = re.compile(
    r"\b(not|never|without|unable|can'?t|cannot|couldn'?t|didn'?t|won'?t|"
    r"haven'?t|hasn'?t|fail(?:ed|s)?)\b|n'?t\b", re.IGNORECASE)

# A universal-COMPLETION claim = a HEAD quantifier asserting the WHOLE scope is done, bound to
# a done-word through FUNCTION WORDS ONLY: "all done", "everything is complete", "the whole
# thing is finished". The head is the genuine unbounded quantifier — "everything", bare "all",
# or the idiom "the whole/entire <scope-noun>". A DETERMINER ("all four phases", "every variant
# tested", "all Wave-2 validators complete") puts a CONTENT noun/number between the quantifier
# and the done-word: that is distributive or scoped/enumerable, NOT the unbounded "the whole
# task is done" claim the advance gate owns. Every one of the six adjudicated real-corpus FPs
# was a determiner ("every variant tested"), a scoped/count claim, or a done-word quoted from
# code (`done|complete|finished`) — this head-vs-determiner split, plus code-span exclusion,
# kills all six without a char-window heuristic. ('complete' alone is a SCOPED done-word, never
# a quantifier — "the design is complete" must not fire; the head quantifier is required.)
_HEAD_UNIVERSAL = (r"(?:everything|all|the\s+(?:whole|entire)\s+"
                   r"(?:thing|lot|project|repo|codebase|suite|implementation|task|job|set))")
_DONE_WORD = (r"(?:done|complete|completed|finished|finalis\w+|finaliz\w+|implemented|built|"
              r"wired|shipped|pushed|merged|deployed|landed|wrapped\s+up|in\s+place|ready)")
# The done-word must sit at a CLAUSE BOUNDARY (end, punctuation, or a coordinating
# conjunction/adverb), NOT be followed by a content noun. "all deployed TOOLS" / "all completed
# TASKS" is the done-word used ADJECTIVALLY inside a noun phrase ("all [adj] [noun]") — a
# distributive determiner, not a predicate (real-corpus FP: "Missing from ALL deployed tools").
# "All done.", "everything is landed and …", "all pushed (digest …)" are predicates -> fire.
_DONE_TRAIL = (r"(?=\s*(?:$|[.,;:!?()\[\]{}<>\"'»—–\-]|"
               r"(?:and|but|so|now|already|then|yet|finally|here|there|up|too|also)\b))")
# Function words permitted between the head and the done-word (copulas, adverbs, conjunctions,
# anaphora). A CONTENT noun/number is NOT here, so a determiner reading breaks the match.
_CONNECTOR = (r"(?:['’]s|is|are|was|were|been|now|then|already|finally|essentially|basically|"
              r"effectively|properly|fully|completely|truly|quite|pretty\s+much|more\s+or\s+less|"
              r"so\s+far|of\s+(?:it|them|that)|here|there|and|but|so|—|–|-|:|;|,)")
_UNIVERSAL_DONE_RX = re.compile(
    r"\b" + _HEAD_UNIVERSAL + r"\b(?:['’]s)?(?:\s+" + _CONNECTOR + r")*\s+"
    + _DONE_WORD + r"\b" + _DONE_TRAIL,
    re.IGNORECASE)
_SENTENCE_SPLIT_RX = re.compile(r"(?<=[.!?])\s|\n")
# A Python-source file gate (".py only — .md is prose"). One home for the 8 security/integrity
# prechecks that key on "is this a .py file" — consolidated from per-file `_TARGET_RX` copies.
_PY_FILE_RX = re.compile(r"\.py$")
# Clearly forward/conditional frames that turn a completion into a promise ("once everything is
# done", "will be all complete") — checked on the clause BEFORE the match only.
_ADV_FORWARD_RX = re.compile(
    r"\b(will|going to|gonna|i'?ll|plan to|once|after|when|until|unless|if|hope to|aim to|"
    r"expect to|about to|to be)\b", re.IGNORECASE)
# An explicit item-range/list ENDING right before the head scopes it ("A-F all built",
# "B.1+B.2+B.3 all complete") — the enumeration shows the bounded set, so the claim is not the
# unbounded "the whole task is done" (real-corpus soft-FPs). A lone number ("Round 5 all done")
# is NOT a list, so it still fires.
_ENUM_BEFORE_HEAD_RX = re.compile(r"[A-Za-z0-9][A-Za-z0-9.]*(?:[-+/][A-Za-z0-9.]+)+\s*$")

# gate.green_claim — a universal/whole-suite test-SUCCESS claim. The SUBJECT must be a whole-suite
# head (tests | suite | CI | build) bound to a success predicate (pass/green). A SUBSET subject
# ('parser tests', 'these tests', 'unit tests') fails open — only a word in _GREEN_UNIVERSAL_PREMOD
# (or nothing) may precede the head. Mirrors _advance_signal's clause discipline (code-quoted,
# negated, forward-framed claims all fail open). Singular 'test' is excluded (one test ≠ the suite).
_GREEN_CLAIM_RX = re.compile(
    r"\b(?P<subj>tests|suite|ci|build)\b"
    r"(?:\s+(?:now|all|still|do|currently|again|once\s+more))*"
    r"\s+(?:are\s+|is\s+|have\s+)?(?:all\s+|now\s+)?"
    r"(?P<pred>pass(?:es|ed|ing)?|succeed(?:s|ed)?|all\s+green|green)\b",
    re.IGNORECASE)
# A pre-modifier OUTSIDE this set scopes the head to a SUBSET ('parser tests') -> silent. 'test'
# admits 'test suite' / 'the test suite'; the rest are universal quantifiers/possessives. A DIGIT
# token before the head ('244 tests', 'all 53 tests') is an ENUMERATED count, handled separately.
_GREEN_UNIVERSAL_PREMOD = frozenset(
    {"the", "all", "every", "our", "my", "full", "entire", "whole", "complete", "test"})

# DELIBERATELY-INDUCED failure framing (lifted from stopcheck_named_test 2026-06-09, two consumers:
# named_test #1 firewall + stale_pass's claim window): a FAILED produced by mutation/teeth testing is
# not a material failure — the test FAILED because the code was intentionally broken to prove it has
# teeth.
_TEETH_FRAME_RX = re.compile(
    r"\b(?:neuter(?:ed|ing|s)?|mutat(?:e|es|ed|ing|ion|ions)|teeth|"
    r"inject(?:ed|ing|s)?\s+(?:a\s+)?bug|deliberately\s+(?:break|broke|broken|fail\w*)|"
    r"intentional(?:ly)?\s+(?:fail\w*|break|broke|broken)|expect(?:ed|s)?\s+(?:it\s+)?to\s+fail|"
    r"should\s+fail\b|\bx?fail(?:ed)?\s+as\s+expected|\bxfail\b|sole.?killer|"
    r"prove\s+(?:the\s+)?(?:test|it)\s+(?:has\s+teeth|catches)|sentinel\s+(?:must\s+)?fail|"
    r"on\s+purpose)\b", re.IGNORECASE)

# §7.1 content-depth: files whose emptiness is itself a legitimate deliverable — claiming you
# "created" one of these is honest even at zero bytes, so an empty one still discharges.
_EMPTY_OK = frozenset({"__init__.py", ".gitkeep", ".keep", ".empty", ".placeholder", "py.typed"})


# --- Retraction vocabulary (relocated from engine.py, §3b/§6 — L0) ---

# A commitment is cleared (status='retracted') only when the assistant DELIBERATELY drops it
# WITH a surfaced reason/scope — mirroring reconcile() (a valid retraction needs a verifiable
# reason) and detect_hidden_retraction() (a drop with NO reason is HIDDEN, not excused, so the
# advance gate still fires). REASON-BOUND on purpose: a bare "dropping X" does NOT clear; an
# unexplained drop is exactly what the advance gate should still catch. Legitimate, explained
# re-prioritization clears -> the advance gate's FP stays low without excusing silent drops.
#
# Hardened against the design-audit's false-clear vectors: negation ("not skipping X"), wrong
# subject ("you won't touch X", "the linter skipped X"), interrogative ("Should I skip X?"),
# conditional ("if tests fail we drop X"), accidental loss ("I accidentally dropped X"),
# recommit ("going to skip X but will add it"), code-fence output, and domain homonyms (SQL
# "drop the temp rows", lazy "defer init to X") — the homonyms fall out of the REASON
# requirement (they carry no retraction scope/reason). The caller clears a commitment only on
# NORMALIZED-EQUALITY membership (the fakeexcuse firewall): retracting cache.py never clears
# auth.py.
_RETRACT_VERB_RX = re.compile(
    r"\b(?:skipp?|dropp?|deferr?|deprioriti[sz]|descop|postpon|shelv|sideline|backlog|"
    r"punt|park|tabl|pull)\w*"
    r"|\bleav(?:e|ing)\b|\bcut\b|\bhold(?:ing)?\s+off\b"
    r"|\bno longer (?:add|need|includ|requir|plan|go)\w*",
    re.IGNORECASE)
# A NEGATED production = a retraction ("do not add X", "won't implement X", "not going to add
# X"). Distinct from negating a retraction verb ("not skipping X" = KEPT) — that stays vetoed.
_RETRACT_NEGPROMISE_RX = re.compile(
    r"\b(?:do not|don'?t|won'?t|will not|not going to|never going to|not planning to)\s+"
    r"(?:add|implement|build|create|writ|includ|wire|introduc|need|do)\w*",
    re.IGNORECASE)
# Post-positive predicate: the retraction sits AFTER the path ("X is out of scope",
# "X can wait", "X was dropped this sprint"). Self-justifying (carries its own scope reason).
_RETRACT_POST_RX = re.compile(
    r"^[\s,]*(?:'?s\b|is|was|are|were|be(?:ing)?)?\s*(?:now|currently|being|already)?\s*"
    r"(?:out of scope|off the table|on (?:the )?back[\s-]?burner|on hold|"
    r"dropped|deprioriti[sz]ed|descoped|shelved|parked|postponed|deferred|tabled|sidelined|"
    r"can wait|punted)\b",
    re.IGNORECASE)
# A reason/scope cue that legitimizes a retraction (reconcile's reason requirement).
_RETRACT_REASON_RX = re.compile(
    r"\bfor (?:now|later|the (?:moment|time being)|a (?:later|future|follow[\s-]?up))\b"
    r"|\bfor (?:this|next|the next|a future) (?:sprint|cycle|release|milestone|pass|pr|round|"
    r"iteration|quarter|version|launch)\b"
    r"|\b(?:next|another|a future|a later) (?:sprint|cycle|release|milestone|pass|pr|round|"
    r"time|iteration)\b"
    r"|\bout of scope\b|\boff the table\b|\bon (?:the )?back[\s-]?burner\b|\bon hold\b"
    r"|\bper your (?:request|note|ask|instruction|call|guidance)\b"
    r"|\byou (?:asked|wanted|requested)\b"
    r"|\bas (?:you )?(?:requested|asked|agreed|wanted)\b|\bwe agreed\b|\bagreed to\b"
    r"|\bdeprioriti[sz]\w*|\buntil \w+|\bfollow[\s-]?up\b|\blater\b|\bcan wait\b"
    r"|\bwe'?ll revisit\b|\brevisit\b|\bdown the line\b|\bback[\s-]?burner\b"
    r"|\bfrom (?:this|the) (?:sprint|milestone|release|pr|cycle|round)\b"
    r"|\bout of (?:this|the) (?:pr|sprint|release|milestone)\b"
    r"|\bnot (?:this|in this) (?:round|sprint|pr|milestone|release)\b"
    r"|\b(?:this|next|the next) (?:sprint|cycle|release|milestone|pass|round|iteration|"
    r"quarter|version)\b",
    re.IGNORECASE)
# Comma/semicolon/colon/newline/em-dash always break a clause; a period breaks ONLY when
# followed by whitespace/end (a sentence stop) — NOT the '.' inside a path like 'cache.py',
# so a coordination list ("dropping a.py and b.py") still binds the verb to both paths.
_RETRACT_CLAUSE_BREAK_RX = re.compile(r"[,;:\n—]|\.(?:\s|$)")
_WRONG_SUBJECT_RX = re.compile(
    r"(?:\byou\b|\bthey\b|\bthe\s+\w+|\b[A-Z][a-z]+)\s*$")
_ACCIDENTAL_RX = re.compile(r"\baccident\w*|\bby mistake\b|\boops\b|\binadvertent\w*", re.I)
# A path explicitly KEPT right after it ("X is still needed", "X stays", "X remains in scope",
# "X is still on the list") is NOT retracted — even if a sibling path was dropped in the same
# breath ("dropping A for now but X is still needed"). Guards the coordination false-clear.
_RETRACT_KEPT_RX = re.compile(
    r"^\s*(?:,?\s*(?:but|however|though|yet))?\s*"
    r"(?:is|are)?\s*(?:still\b|stays?\b|remains?\b|kept\b|(?:is\s+)?needed\b|required\b|"
    r"on (?:the|our) (?:list|board|radar|roadmap)\b|in scope\b)", re.IGNORECASE)
# An adversative between the verb and the path ("dropping A ... but X") contrasts X away from
# the drop — the verb governs the earlier clause, not X.
_RETRACT_ADVERSATIVE_RX = re.compile(r"\b(?:but|however|though|whereas|yet|while)\b", re.IGNORECASE)
