"""Labeled recall+precision probe for commitments.source_commitment + engine._discharged.

source_commitment must record a commitment ONLY for a first-person, file-shaped, forward
production promise whose produce verb GOVERNS the path — never for a mere mention. Over-sourcing
a phantom commitment is the advance gate's dominant real-corpus FP driver: a path in an ASCII
tree, a markdown table cell, an identifier ("build_live_scorer"), a noun-modifier ("CLAUDE.md
convention"), a read verb ("reading X"), a third-party/subagent subject ("the fork writing X"),
an adverbial gerund ("before adding entries to X"), a conditional offer ("if you greenlight, I
can write X"), or a bare lowercase word detect_locations over-matched as a dotless file
("a license-check rule"). Each INERT case below is an ACTUAL adjudicated real-session FP.

_discharged must clear a commitment whose path is a path-component SUFFIX of a touched key
(relative/bare commitment vs absolute write) while preserving the fakeexcuse firewall
(auth.py never matches auth_helper.py). The two halves together are a contamination canary.
"""
from makoto.commitments import source_commitment as S, _is_file_shaped
from makoto.checks._shared import _discharged


# --- RECALL: a genuine first-person/imperative file-shaped promise MUST source ---------------
SOURCES = [
    "add rate-limit to `src/auth.py`",
    "I'll add rate limiting to `src/auth.py`",
    "Next I will add caching in `src/cache.py`.",
    "add x to `a/b.py`",
    "I'll write `docs/design.md` for this.",
    "We'll create `LICENSE` at the root.",          # known dotless convention, capitalized
    "I'll add `auth.py` (rate limiting + retries).",  # descriptive parenthetical -> still a promise
    "I'll add an opt-in flag to `config.py`.",        # 'opt-in' modifies the flag, not the file
    "It could add value, so I'll build `scorer.py`.",  # 'could add' is about value, not a proposal verb
]


# --- PRECISION: each adjudicated phantom-commitment shape MUST stay inert ---------------------
INERT = [
    "│   └── stop.sh   ← gate: read/write ratio breach",        # file-tree diagram line
    "| **B. Side-by-side** | Build `valuable.md` (curated) |",  # markdown table row
    "comparing `scoring.py` (my `build_live_scorer`) vs `score.py`",  # identifier, not the verb
    "If you greenlight, I can write the spec to `docs/x/design.md` now.",  # conditional offer
    "the agents are reading `CHEATS.md` / `DRIFT-AND-CARE.md` to build the index",  # read verb
    "Still running: the fold fork writing `DIGEST-V4-MASTER.md`.",   # third-party/subagent subject
    "Adopt as the bar before adding any new entries to valuable.md.",  # adverbial gerund
    "for free-prose claims it leans on a CLAUDE.md convention and checks",  # noun-modifier mention
    "I'll add a license-check rule to the aggregator prompts",  # bare lowercase word, not a file
    "I added rate limiting to src/auth.py",          # past production -> a completion, not a promise
    "I won't add `src/old.py` this sprint",          # negated promise -> a retraction
    "See `src/auth.py` for the existing implementation.",       # reference, no produce verb
    # an OPTIONAL feature offered in a plan-proposal, marked optional in a parenthetical ON the
    # path -> an offer, not a firm promise (the reproduced advance-gate corpus FP, session d2595e7a)
    "Add `claude_harness/heavy/cache_semantic.py` (Apache-2.0 sentence-transformers, opt-in via "
    "`pip install claude-harness[heavy]`). Stacks on top of free exact-match.",
    "Add `config.py` (optional).",                   # explicit optional qualifier on the path
    # an "Add X" bullet under a "New Task N.M" PROPOSAL header in a plan-audit menu the AI presents
    # for the user to choose from ("If you say 'do all 4'...") -> a proposed task, not a firm promise.
    # The 2nd reproduced advance-gate corpus FP, same session d2595e7a, lookup.py (no inline marker).
    "**4. New Task 15.5 — paid lookup tiebreak**\n\nAdd `claude_harness/paid/lookup.py` that wraps "
    "free.lookup with cross-encoder rerank on top-3 ties + Haiku final tiebreak.",
    # a path inside a fenced ```code block``` is a command/demo, displayed not promised — here the
    # redirect target of a `git reset --hard` demo, sourced only because "MY ... WORK" trips
    # first-person. The 3rd reproduced advance-gate corpus FP, same session d2595e7a.
    '```bash\necho "MY UNSAVED CRITICAL WORK — three days of writing" > critical_notes.txt\nls\n```',
    # an "Add X:" bullet under a "## What's worth building / concrete additions" proposal-menu
    # header -> a recommendation the AI never builds, not a firm promise. The 4th reproduced
    # advance-gate corpus FP, same session d2595e7a (compression_cache.py, never touched).
    "## What's worth building\n\nThree concrete additions, in priority order:\n\n### 1. Compression "
    "cache (HIGHEST leverage, easiest)\n\nAdd `claude_harness/substrate/compression_cache.py`:",
]


def test_recall_genuine_promises_source():
    misses = [t for t in SOURCES if S(t) is None]
    assert not misses, f"recall regression — these genuine promises did not source: {misses}"


def test_precision_phantom_commitment_shapes_stay_inert():
    fires = [t for t in INERT if S(t) is not None]
    assert not fires, f"precision regression — these mentions wrongly sourced: {fires}"


def test_sourcing_is_neither_source_all_nor_source_none():
    sourced_any = any(S(t) for t in SOURCES)
    inert_any = any(S(t) is None for t in INERT)
    assert sourced_any and inert_any, "sourcing collapsed to a constant — voided"


# --- _is_file_shaped: a commitment location is a real FILE token, not a code identifier --------
# Regression (live advance-gate FP, 2026-06-02): _is_file_shaped accepted ANY dotted token, so a
# class attribute ('Finding.source_event_id'), a method ref ('obj.method'), a class ('Module.Class'),
# a version ('v1.2'), or a pattern id ('1.4') were mis-read as filenames and sourced as phantom
# commitments the advance gate then false-fired on. A dotted token is a file ONLY if its last
# segment is a plausible (lowercase, non-numeric) file extension; a slash-command ('/loop') is a
# command token, not a path. FN-critical: every real file token must STILL be file-shaped.
_FILE_SHAPED = ["README.md", "src/auth.py", "config.json", "a/b/c.py", "my.config.json",
                "style.scss", "component.jsx", "LICENSE", "Makefile", "pyproject.toml",
                "data.yaml", "x.h", "notes.txt"]
_NOT_FILE_SHAPED = ["Finding.source_event_id", "obj.method", "Module.Class", "schema.load_prechecks",
                    "v1.2", "1.4", "1.33", "/loop", "/makoto:status", "main", "detect_location"]


def test_is_file_shaped_accepts_real_files_rejects_code_identifiers():
    fn = [t for t in _FILE_SHAPED if not _is_file_shaped(t)]
    fp = [t for t in _NOT_FILE_SHAPED if _is_file_shaped(t)]
    assert not fn, f"FN — real file tokens wrongly rejected (would drop genuine commitments): {fn}"
    assert not fp, f"FP — code identifiers/commands/version-ids wrongly accepted as files: {fp}"


# --- _discharged: path-component-suffix resolution + the fakeexcuse firewall ------------------
def test_discharge_bare_commitment_vs_absolute_write():
    # a bare/relative commitment discharges against the absolute path actually written
    assert _discharged("settings.json", {"/Users/x/.claude/settings.json"}, None) is True
    assert _discharged("docs/CONFIG.md", {"/Users/x/repo/docs/CONFIG.md"}, None) is True
    assert _discharged("~/.claude/CLAUDE.md", {"CLAUDE.md"}, None) is True   # bidirectional + ~ strip


def test_discharge_preserves_fakeexcuse_firewall():
    # suffix match is at a path-SEPARATOR boundary: auth.py is NOT discharged by auth_helper.py
    assert _discharged("auth.py", {"src/auth_helper.py"}, None) is False
    assert _discharged("src/auth.py", {"lib/auth.py"}, None) is False        # two full components differ
    assert _discharged("totally_unique_zzz.py", {"src/auth.py", "src/cache.py"}, None) is False


def test_discharge_exact_and_empty():
    assert _discharged("src/auth.py", {"src/auth.py"}, None) is True
    assert _discharged("src/auth.py", set(), None) is False


# --- line-level pinning: _non_prose_line + _promise_location slice boundary --------------------
# A markdown TABLE row (>=2 cell pipes) is a listing, not a sentence, even when a produce verb
# ("Add") sits line-initial AHEAD of the path and the pipes trail it (so _GOVERN_BREAK_RX, which
# only scans the text BEFORE the path, never sees them). _non_prose_line is the SOLE guard that
# examines whole-line pipe count, so this path must stay inert. Pins commitments.py:111 — if the
# >=2-pipe branch were dropped (return False), this table row would wrongly source `out.py`.
def test_table_row_with_trailing_pipes_stays_inert():
    assert S("Add `out.py` | extra | cells |") is None


# A file-tree glyph on the path's line marks it a file-listing, not prose — even with a real
# first-person subject ("I") and produce verb ("create") in the same line, because the glyph
# precedes the verb (not a govern-break between verb and path). _non_prose_line flags the glyph
# OR the pipe count; either alone suffices. Pins commitments.py:111 — if the `or` were weakened to
# `and` (requiring BOTH glyph AND >=2 pipes), this glyph-only line would wrongly source `lib/z.py`.
def test_tree_glyph_line_alone_stays_inert():
    assert S("─ I will create `lib/z.py` now") is None


# The non-prose check runs over the path's OWN line only — the slice `text[ls:le]` where `le` is
# the next newline (or end-of-text when there is none). A genuine first-person promise on a prose
# line must source even when the FOLLOWING line is a markdown table row. Pins commitments.py:144 —
# if `le != -1` were flipped to `le == -1`, the slice would extend past the line end to len(text),
# pulling the trailing pipe-row in, mis-flagging the prose line non-prose, and dropping the promise.
def test_prose_line_sources_despite_following_table_row():
    got = S("I'll add `core/run.py` now\n| a | b | c |\nmore")
    assert got is not None
    assert got["location"] == "core/run.py"
