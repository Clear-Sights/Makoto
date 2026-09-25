"""Shared vocabulary: PreCheck + Finding dataclasses, plus the L0 lexicons.

PreCheck fields are the minimum data needed at hot-path dispatch:
  id / fire_level / description / retry_hint / predicate_module / keywords.

`PreCheck` survives as a convenience dataclass for hand-constructing synthetic pattern fixtures
in unit tests that call a predicate directly without going through the loader; the live Pre-tier
catalog is `registry.load_precheck_catalog()`, whose rows are `Check` instances, not `PreCheck`
instances -- the two are structurally similar but not the same type, and nothing at runtime
converts one into the other.

L0 lexicons — the single home for makoto's regexes + word-sets. Pure data: compiled regexes +
frozensets, no in-package imports (L0 of the layered DAG). Detectors, gates, and primitives
import these by name so one edit governs every surface.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PreCheck:
    """one declarative pattern definition -- test-fixture convenience shape ONLY (the live
    Pre-tier catalog is `registry.load_precheck_catalog()`, whose rows are `Check` instances, not
    this class)."""
    id: str
    fire_level: str                                          # "error" ONLY, by convention
    description: str                                          # human-facing; interpolated into Finding.message
    retry_hint: str = ""                                      # agent-facing imperative remediation hint
    predicate_module: str = ""                                # dotted path to the predicate function
    keywords: list[str] = field(default_factory=list)         # substring prefilter triggers; >=1 for active patterns


@dataclass(frozen=True)
class Finding:
    """one finding emitted by a predicate — what fired, where, with what message."""
    pattern_id: str
    file: str
    line: int
    level: str
    message: str
    retry_hint: str = ""
    snippet: str = ""
    source_event_id: int = 0   # provenance: the events.id this finding was derived from.
                               # Stamped centrally at the dispatch boundary via
                               # dataclasses.replace, so predicates stay pure detectors. A 0
                               # marks a finding built outside the hot path (a direct unit call).


# --- L0 lexicons (verbatim from core/lexicons.py) ------------------------------

# File extensions recognized by the location detector. Kept at L0 because both the detector
# and shared path-suffix discharge logic must recognize precisely the same extension set.
_PATH_EXT = (
    r"py|pyi|md|rst|txt|toml|json|jsonl|ndjson|ya?ml|ini|cfg|conf|env|lock|"
    r"sh|bash|zsh|fish|js|jsx|mjs|cjs|ts|tsx|rs|go|rb|java|kt|swift|c|h|hpp|cc|cpp|"
    r"sql|html?|css|scss|sass|xml|csv|tsv|sock|proto|graphql|tf|svg|ipynb|dockerfile"
)

_NEGATION_RX = re.compile(r"\b(not|never|no)\b|n['’]t\b", re.IGNORECASE)

# Universal exemption marker: the bundled CLAUDE.md tells the AI that when a flagged shape is
# LEGITIMATE, annotate it with
# `makoto-allow: <reason>` and makoto will not flag it. This makes every content-scan
# pattern FP-exemptable EVERYWHERE — a compliant AI marks its legitimate cases, so only
# UNMARKED (likely-violation) content fires. The marker is plain-text + case-insensitive so it
# works in any language/comment style. It is file-level (a deliberate evader
# who writes a false `makoto-allow: <reason>` leaves an on-the-record, auditable rationale).
# Structured marker (2026-06-01, §7.5b): `makoto-allow:` followed by a non-empty reason. A bare
# `makoto-allow` with no colon/reason no longer exempts — an exemption without an on-the-record
# rationale is a reasonless laundering token, which is itself an empty word.
_MAKOTO_ALLOW_RX = re.compile(r"makoto-allow\s*:\s*\S", re.IGNORECASE)
# Reason CAPTURE (the audit half): the rationale text after the colon, for the on-the-record
# exemption row. Same trigger as _MAKOTO_ALLOW_RX (colon + a non-empty reason) — kept separate so
# the hot boolean check stays a bare search and only the recording path pays for the capture.
_MAKOTO_ALLOW_REASON_RX = re.compile(r"makoto-allow\s*:\s*(\S.*)", re.IGNORECASE)

# ---- Test-runner provenance + failure-verdict (shared by the ledger + the green-claim gate) ----
# _TEST_RUNNER_RX is the legacy lexical runner vocabulary, retained as an import-compatible
# export; actual command provenance is argv-structured in core._shell._command_runs_tests, so a
# runner word inside `cat pytest.log` or quoted prose is not an invocation.
# kit.is_failing_testrun asks: does test-runner OUTPUT show >=1 REAL failure? xfail-safe since
# `\bfailed\b` cannot match inside `xfailed`/`xpassed` (no word boundary).
_TEST_RUNNER_RX = re.compile(
    r"\b("
    r"pytest|py\.test|python[0-9.]*\s+-m\s+(?:pytest|unittest)|-m\s+unittest|"
    # A script kept under a tests/ directory, run by its interpreter: how the trees run their own
    # checks (`python3 zero/tests/probe.py G`, `bash zero/tests/run.sh`). Without it those runs are
    # no verifier at all and a vacuous one among them is never asked for a red run (0 of 20).
    r"(?:python[0-9.]*|bash|sh)\s+(?:\S*/)?tests?/\S+?\.(?:py|sh)|"
    r"nox|tox|"
    r"jest|vitest|mocha|ava|jasmine|"
    r"go\s+test|cargo\s+(?:test|nextest)|"
    r"npm\s+(?:run\s+)?test|yarn\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|"
    r"rspec|phpunit|ctest|gradlew?\s+test|mvn\s+test|"
    r"make\s+test|just\s+test|rails\s+test|"
    r"scripts/falsify|scripts/cert|scripts/connectivity|measure_corpus_fp"
    r")\b",
    re.IGNORECASE)

# A SUMMARY/count denoting >=1 real failure or error. The count-first alternatives cover
# pytest/jest (`N failed`), rspec (`N failures`), and mocha (`N failing`); label-first covers
# Maven/PHPUnit (`Failures: N`). A traceback is a failure only when no later positive pass summary
# resolves it -- runners can print a caught cleanup traceback and still finish green.
_FAILURE_SUMMARY_RX = re.compile(
    r"\b[1-9]\d*\s+(?:failed|failures?|failing)\b"
    r"|\b[1-9]\d*\s+errors?\b"
    r"|\b(?:failures?|errors?)\s*:\s*[1-9]\d*\b"
    r"|^FAILURES!\s*$"
    r"|Traceback \(most recent call last\):(?![\s\S]*\b[1-9]\d*\s+passed\b)",
    re.IGNORECASE | re.MULTILINE)

# Positive test-run evidence. Canon's green atom combines this with a recognized runner command
# and the protocol exit status (when present); output merely lacking a failure is never success.
_SUCCESS_SUMMARY_RX = re.compile(
    r"\b[1-9]\d*\s+passed\b"                       # pytest/jest
    r"|\b[1-9]\d*\s+passing\b"                     # mocha
    r"|\b[1-9]\d*\s+examples?,\s+0\s+failures?\b" # rspec
    r"|^test result:\s+ok\b"                       # cargo
    r"|^ok\s+\S+"                                  # go test
    r"|^BUILD SUCCESS\b"                           # Maven/Gradle
    r"|^OK \([1-9]\d*\s+tests?\b",                 # PHPUnit
    re.IGNORECASE | re.MULTILINE)

# Per-test / per-package FAILURE markers — case-SENSITIVE (uppercase runner markers only), so prose
# like "failed to connect" never matches. Anchored at line start.
_FAILURE_MARKER_RX = re.compile(
    r"^(?:FAILED\s+\S|ERROR\s+\S|FAIL\b|={2,}\s*FAILURES\s*={2,}|={2,}\s*ERRORS\s*={2,})",
    re.MULTILINE)

# ANSI SGR color codes. vitest/jest colorize the summary, and the SGR terminator 'm' is a WORD
# char that abuts the count ('\x1b[31m2 failed'), killing the \b before `[1-9]\d* failed` so a
# REAL failing run reads as green. Stripped before failure detection (is_failing_testrun).
_ANSI_SGR_RX = re.compile(r"\x1b\[[0-9;:]*m")

_CITATION_RX = re.compile(
    r'\b([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+(?:et al\.\s+)?(\d{4})\b'
)

# Capitalized English words that match the Author position of the regex but aren't author
# surnames -- 'Saved 2026' (date prefix), 'The 2023' (article+year), etc. measured to drive a
# 40% FP rate on content.phantom_citation without this filter.
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
    "Copyright", "Since", "Merged", "Reviewed", "Bumped",
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
    "Item", "Issue", "Section", "Chapter", "Part", "Page",
})


# --- Stop-gate vocabulary ---

# A PRODUCTION claim asserts the assistant PRODUCED/changed a file (past/perfective):
# "wrote / created / added / saved / updated / implemented ... <path>". The completion gate
# fires only when such a verb GOVERNS a located path that has no trace — never on a mere
# co-occurrence of a done-word and a path (this avoided a measured 9% completion-gate FP:
# displaying code, listing a subagent's deliverable, an incidental path mention). A produce verb
# within _BIND_BEFORE chars before the path binds -- unless a forward frame or a negation sits
# right against it. `built(?!-)` so the adjective "built-in" does not false-match. The gate
# requires the verb to sit BEFORE the path and govern it directly — "I created `X`" — never the
# passive "`X` was created".
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
# A full ```fenced``` code block (DOTALL: the span crosses newlines). L0 SINGLE SOURCE for
# fenced-span extraction — substrate.claims._code_spans (fences + inline backticks) consumes
# this exact object, so the fence regex lives in one place. Distinct from the `_FENCE_RX`
# line-anchored parity marker (a different algorithm), which lives in checks.relativePathCitation.
_FENCE_SPAN_RX = re.compile(r"```.*?```", re.DOTALL)

# UNAMBIGUOUS integrity / verification / audit vocabulary (a raw alternation STRING, not a
# compiled regex — each consumer anchors it differently). L0 SINGLE SOURCE for the
# integrity-named-concept word-set, consumed by checks.integritySuppressionFlag and
# checks.envGatedAudit. Deliberately NARROW: broad stems (validat/guard/enforc/seal/complian)
# were dropped after a reviewer cited concrete non-integrity toggles they would block
# (`input_validation_skip` = web-form validation). Every stem here names the
# integrity/verification/audit of a CHECK, not a generic policy — so a blocking fire stays MATERIAL.
_INTEG_VOCAB = r"audit|verif|integrit|attest|checksum|signatur|tamper|provenance"
_FORWARD_FRAME_RX = re.compile(
    r"\b(will|going to|gonna|i'?ll|plan to|need to|about to|next|todo|should|"
    r"would|hope to|want to|let'?s)\b", re.IGNORECASE)
_NEG_FRAME_RX = re.compile(
    r"\b(not|never|without|unable|can'?t|cannot|couldn'?t|didn'?t|won'?t|"
    r"haven'?t|hasn'?t|fail(?:ed|s)?)\b|n'?t\b", re.IGNORECASE)

_SENTENCE_SPLIT_RX = re.compile(r"(?<=[.!?])\s|\n")
# A Python-source file gate (".py only — .md is prose"). One home for the security/integrity
# checks that key on "is this a .py file" — consolidated from per-file `_TARGET_RX` copies
# (checks.envGatedAudit imports it under that name).
_PY_FILE_RX = re.compile(r"\.py$")
# Clearly forward/conditional frames that turn a completion into a promise ("once everything is
# done", "will be all complete") — checked on the clause BEFORE the match only.
_ADV_FORWARD_RX = re.compile(
    r"\b(will|going to|gonna|i'?ll|plan to|once|after|when|until|unless|if|hope to|aim to|"
    r"expect to|about to|to be)\b", re.IGNORECASE)
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

# ---- recorded per-test verdicts: the EVIDENCE side of a named-test claim ----------------------
# A parser is lexicon, and lexicon is rank 0, where every layer above can reach it.

# A bare pytest-style test identifier. Exact token; coreference is by exact string equality.
_TESTNAME_RX = re.compile(r"\btest_[A-Za-z0-9_]+")

# Recorded per-test FAILED / PASSED markers (the evidence side). Case-SENSITIVE runner tokens so
# prose like "failed to connect" never matches. Both orderings (verdict leads / trails the id).
# The lead forms tolerate a line PREFIX before the verdict token (pytest-xdist emits
# "[gw0] [100%] PASSED tests/…::test_x"). The id captures the MODULE PATH (a bare-name key would
# let tests/a's failure deny a claim about tests/b's same-named green test) and any
# PARAMETRIZATION suffix (stripping it would let a green test_charge[eur] discharge a red
# test_charge[usd]).
_TEST_ID = r"(?P<path>\S*?)::(?P<name>test_[A-Za-z0-9_]+(?:\[[^\]\n]*\])?)"
_REC_FAIL_LEAD_RX = re.compile(r"^[^\n]*?\b(?:FAILED|ERROR)\s+" + _TEST_ID, re.MULTILINE)
_REC_FAIL_TRAIL_RX = re.compile(_TEST_ID + r"[^\n]*?\b(?:FAILED|ERROR)\b", re.MULTILINE)
_REC_PASS_LEAD_RX = re.compile(r"^[^\n]*?\bPASSED\s+" + _TEST_ID, re.MULTILINE)
_REC_PASS_TRAIL_RX = re.compile(_TEST_ID + r"[^\n]*?\bPASSED\b", re.MULTILINE)
# (#1)/(#2) teeth-frame SCOPE: the frame voids only verdict records in its own vicinity (this
# many chars around the record), never the whole response — one incidental teeth word in a
# traceback must not discard every recorded failure in the run, and symmetrically a PASSED
# recorded inside deliberately-induced-failure framing is no material discharge either.
_TEETH_SCOPE_BEFORE = 200
_TEETH_SCOPE_AFTER = 120


def _recorded_names(text: str, lead_rx, trail_rx) -> set:
    """Shared shape of recorded_failed_names/recorded_passed_names -- same extraction, different
    verdict regex pair."""
    if not text:
        return set()
    return ({m.group("name") for m in lead_rx.finditer(text)}
            | {m.group("name") for m in trail_rx.finditer(text)})


def recorded_failed_names(text: str) -> set:
    """Exact test names recorded as FAILED/ERROR in a tool output (both verdict orderings)."""
    return _recorded_names(text, _REC_FAIL_LEAD_RX, _REC_FAIL_TRAIL_RX)


def recorded_passed_names(text: str) -> set:
    """Exact test names recorded as PASSED (the discharge evidence; both verdict orderings)."""
    return _recorded_names(text, _REC_PASS_LEAD_RX, _REC_PASS_TRAIL_RX)


# DELIBERATELY-INDUCED failure framing (two consumers: checks.namedTestTeeth's firewall +
# checks.stalePytestCache's claim window): a FAILED produced by mutation/teeth testing is not a
# material failure — the test FAILED because the code was intentionally broken to prove it has
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


# --- gate.claimed_running vocabulary (an ongoing process/service liveness claim) ---
# A CLOSED set of process-referring subjects — mirrors _GREEN_CLAIM_RX's closed-subject-head
# shape: an unrelated/unlisted subject fails open (precision over recall, same tradeoff every
# closed-lexicon gate in this file makes).
_RUNNING_SUBJECT = (
    r"(?:it|this|that|the\s+(?:dev(?:elopment)?\s+)?server|the\s+app(?:lication)?|"
    r"the\s+service|the\s+api|the\s+backend|the\s+frontend|the\s+process|"
    r"the\s+container|the\s+daemon|the\s+worker|the\s+job|the\s+bot|the\s+site|"
    r"the\s+database|the\s+program)"
)
# Present-tense copula ONLY (is/are/'s/'re) — 'was/were running' is an honest past-tense
# admission (possibly of a crash) and fails open by construction; no separate past-tense veto
# needed. `\s*` (not `\s+`) between subject and copula so a fused contraction ("it's", "that's")
# still binds — the copula alternation itself is the effective right-boundary (no spurious
# mid-word match: "itinerary" cannot satisfy `(?:is|are|'s|'re)` at the position right after
# "it", so that alternative fails there and the engine moves on).
_RUNNING_PRED = (
    r"(?:is|are|['’]s|['’]re)\s*"
    r"(?:now\s+|currently\s+|already\s+|successfully\s+|back\s+|still\s+|fully\s+)?"
    r"(?:up\s+and\s+running|running|live|up|listening|serving|operational)\b"
)
# Two subject-less alternatives for banner-style status prose ("Now running.", "listening on
# port 5173", "serving at http://...") — each anchored on a recency/port/URL token so a bare
# "serving" alone (too generic on its own) cannot match without one.
_RUNNING_CLAIM_RX = re.compile(
    rf"\b{_RUNNING_SUBJECT}\s*{_RUNNING_PRED}"
    r"|\bnow\s+(?:running|listening|serving)\b"
    r"|\b(?:running|listening|serving)\s+(?:on|at)\s+(?:https?://|port\s+|:)\S+",
    re.IGNORECASE)
# A first-person process-lifecycle ACTION verb (past/perfective) — checks.claimedRunningAbsent
# requires this to co-occur ANYWHERE in the claim text as a precision firewall: generic
# explanatory prose ("Vite's dev server is running on port 5173 by default") essentially never
# ALSO narrates the assistant itself starting something, so this co-occurrence kills that FP
# class at the cost of a documented recall bound (a bare re-confirmation with no start narrated
# in the same turn, e.g. "checked again — still running fine", fails open). State words
# (running/live/up/listening/serving) are deliberately EXCLUDED from this list — including one
# would make the co-occurrence requirement circular against _RUNNING_CLAIM_RX's own predicate.
_PROCESS_START_VERB_RX = re.compile(
    r"\bI(?:['’]ve|['’]d|\s+have)?\s+(?:just\s+)?(?:started|launched|spun\s+up|spinning\s+up|"
    r"brought\s+up|booted|kicked\s+off|fired\s+up|restarted|re-started|ran|deployed|stood\s+up)\b",
    re.IGNORECASE)
# Bash-command classifier for "this call concerns a long-lived process's lifecycle" — open-world,
# deliberately broad like _TEST_RUNNER_RX: an unlisted launcher/healthcheck shape is a documented
# RECALL bound, never a false-block source. Three families: shell backgrounding operators (the
# one truly ecosystem-agnostic signal, present regardless of language/framework), common
# launch/serve commands across several ecosystems, and common liveness-check commands (curl/ps/
# docker ps/...) — the strongest evidence, since a healthcheck's own exit code is a direct
# verdict, not merely "we tried to start something".
_PROCESS_LIFECYCLE_CMD_RX = re.compile(
    r"&\s*$|\bnohup\b|\bdisown\b|\bsetsid\b|"
    r"\bpm2\s+(?:start|restart)\b|\bdocker\s+(?:run|start|compose\s+up)\b|\bdocker-compose\s+up\b|"
    r"\bsystemctl\s+(?:start|restart)\b|\bservice\s+\S+\s+start\b|"
    r"\bnpm\s+(?:run\s+)?(?:start|dev|serve)\b|\byarn\s+(?:start|dev)\b|\bpnpm\s+(?:start|dev)\b|"
    r"\bflask\s+run\b|\brails\s+(?:server|s)\b|\b(?:uvicorn|gunicorn|hypercorn)\b|"
    r"\bpython[0-9.]*\s+-m\s+http\.server\b|\bmanage\.py\s+runserver\b|"
    r"\bnode\s+\S+\.js\b|\bnext\s+(?:dev|start)\b|\bvite\b|"
    r"\bcargo\s+run\b|\bgo\s+run\b|\bjava\s+-jar\b|"
    r"\bcurl\b|\bwget\b|\bnc\s+-z\b|\blsof\s+-i\b|\bnetstat\b|\bss\s+-\w*l\w*\b|"
    r"\bps\s+(?:aux|-ef|-e)\b|\bpgrep\b|\bdocker\s+ps\b|\bsystemctl\s+status\b|\bpm2\s+(?:status|list)\b",
    re.IGNORECASE)


# --- gate.claimed_shipped vocabulary (a completed remote/external mutation claim) ---
# Two deliberately CLOSED claim families. The action family binds a first-person subject to a
# past/perfective shipping verb; the second alternative permits the conventional subject-less
# status-report form only at a sentence/list-item boundary ("Pushed it to main.", "Merged #42.").
# That boundary is the precision firewall: ordinary explanatory prose such as "the hook pushes
# artifacts" and third-party narration cannot acquire an implied first-person subject merely by
# containing a ship-shaped word. Present/base forms are absent, so "this deploys to a CDN" is
# inert by construction.
_SHIPPED_ACTION_CLAIM_RX = re.compile(
    r"\bI(?:['’]ve|\s+have)?\s+(?:just\s+|now\s+|successfully\s+|already\s+)?"
    r"(?:pushed|merged|published|deployed|shipped|released)\b"
    r"|(?:^|(?<=[.!?\n]))[ \t]*(?:[-*]\s+)?"
    r"(?:pushed|merged|published|deployed|shipped|released)\b",
    re.IGNORECASE | re.MULTILINE)
# State claims use present tense plus a CLOSED remote-result predicate. "Live" is anchored by
# `now`/`already` because bare "it is live" is routinely descriptive (a fixture, connection, or
# UI state), while "it's live now" is the high-confidence completion report this gate owns.
# Past copulas are deliberately absent: "it was merged" is passive/third-party history. The
# subject set likewise excludes arbitrary nouns, accepting the recall bound rather than turning
# every technical use of "published"/"deployed" into a claim about the assistant's own action.
_SHIPPED_STATE_CLAIM_RX = re.compile(
    r"\b(?:it|this|that|the\s+(?:pr|pull\s+request|change|commit|package|release|"
    r"deployment|site|app(?:lication)?|service))\s*"
    r"(?:is|are|['’]s|['’]re)\s*"
    r"(?:(?:now|already|successfully)\s+"
    r"(?:merged|published|deployed|shipped|released|live)"
    r"|live\s+now)\b",
    re.IGNORECASE)
# Bash evidence for this gate is argv-structured, not lexical, and so is NOT vocabulary: it is
# intentionally narrower than canon's destructive classifier (any real `git push` mutates a remote,
# not only a forced push), and checks.claimedShippedAbsent gets it from
# core._shell._command_pushes_git, which parses the argv and vetoes `-n`/`--dry-run`.
