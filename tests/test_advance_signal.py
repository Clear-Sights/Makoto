"""Labeled recall+precision probe for engine._advance_signal — the advance gate's claim
detector (a HEAD universal quantifier binding a done-word through function words only).

This is a permanent contamination canary: the FIRE set (genuine universal-completion claims)
pins RECALL, the INERT set (the adjudicated real-corpus FP shapes) pins PRECISION. A
suppress-to-zero regression reds every FIRE case; a fire-on-everything regression reds every
INERT case. Both ends are required to pass — neither cheat wins on both axes.

The INERT cases are not invented: each is an actual false-fire driver adjudicated from a real
~/.claude session corpus (distributive determiner, adjectival done-word, code-quoted done-word,
enumerated/scoped claim, forward frame, negation, scoped done, bare phase-transition).
"""
from makoto.checks.undischargedCommitment import _advance_signal, advance_gate


# --- RECALL: genuine universal-completion claims MUST fire ---------------------------------
FIRE = [
    "All done.",
    "Everything is done — all complete.",          # the canonical committed claim
    "Everything is complete.",
    "all complete",
    "everything's finished",
    "All landed.",                                  # real corpus (stop.sh)
    "Everything is landed and the loop is healthy.",  # real corpus (settings.json)
    "All pushed (digest `fe775`).",                 # real corpus (DRIFT)
    "everything is now done",
    "the whole thing is finished",
    "the entire project is complete",
    "everything is implemented",
    "all merged and deployed",
    "All wired up.",                                # phrasal completion (trailing 'up')
    "Everything is wrapped up.",                    # multi-word done-word
    "all in place",                                 # multi-word done-word
]


# --- PRECISION: each adjudicated FP shape must stay INERT ----------------------------------
INERT = [
    # distributive determiner / adjectival done-word (head modifies a content noun)
    "Missing from ALL deployed tools (= Digest's niche).",   # real corpus (bench_lib): adjectival
    "RESULTS-INDEX recording every variant tested today.",   # real corpus (SKILL.md): "every"+noun
    "All four phases pre-staged, 14 agents still in flight.",  # real corpus (bench_lib): "all four"
    "each fork reads the outputs then runs the step",        # "each"+noun, distributive
    "the entire file was scanned for drift",                 # "entire file" not a scope-idiom head
    "all completed tasks remain open in the tracker",        # adjectival "completed tasks"
    # enumerated / scoped claim (explicit bounded set)
    "A-F all built and tested. Your move.",                  # real corpus (digest-v3): item-range
    "architectural-batch final tally (B.1+B.2+B.3 all complete):",  # real corpus (setup.py)
    "All 5 of 5 tasks done.",                                # number between head and done-word
    # scoped done (no universal head)
    "the design is complete",
    "Done with the parser refactor.",
    # done-word quoted from code, not the AI's own prose
    "response_claims_done checks for a done-word (`done|complete|finished`).",  # real corpus (settings)
    "```\nAll done.\n```",                                   # fenced output
    # negation / forward frame / bare transition / meta
    "Not everything is done yet, moving on.",
    "nothing is complete",
    "Once everything is done, ship it.",
    "I'll ping you when everything is complete.",
    "Moving on to the next phase.",
    "I'm not 100% sure how Claude Code signals \"done\".",   # real corpus (setup.py): meta-discussion
]


def test_recall_universal_completion_claims_fire():
    misses = [t for t in FIRE if not _advance_signal(t)]
    assert not misses, f"recall regression — these genuine claims did not fire: {misses}"


def test_precision_adjudicated_fp_shapes_stay_inert():
    false_fires = [t for t in INERT if _advance_signal(t)]
    assert not false_fires, f"precision regression — these FP shapes fired: {false_fires}"


def test_detector_is_neither_fire_all_nor_fire_none():
    # contamination canary: a real classifier fires on the FIRE set AND stays silent on INERT
    fired_any = any(_advance_signal(t) for t in FIRE)
    silent_any = any(not _advance_signal(t) for t in INERT)
    assert fired_any and silent_any, "detector collapsed to a constant — voided"


def test_empty_and_none_are_inert():
    assert _advance_signal("") is False
    assert _advance_signal(None) is False



# --- advance_gate discharge: relocation tolerance (direct gate-function calls) -------------
_UNIV = "Everything is wired up now."


def test_relocated_commitment_does_not_false_fire():
    """FP fix: a universal-completion claim while the open commitment was satisfied at a RENAMED
    path (src/parser.py -> src/parser_v2.py) must NOT fire — the path moved, the work was done."""
    f = advance_gate(_UNIV, [{"location": "src/parser.py"}],
                     touched_keys={"src/parser_v2.py"}, fs_exists=lambda p: False)
    assert f is None


def test_genuinely_dropped_commitment_still_fires():
    """TP intact: a universal claim with a commitment never touched and not on disk -> fires."""
    f = advance_gate(_UNIV, [{"location": "src/missing.py"}],
                     touched_keys=set(), fs_exists=lambda p: False)
    assert f is not None and f.pattern_id == "gate.advance"


def test_unrelated_touch_is_not_a_rename_and_still_fires():
    """TP intact: an unrelated touched file is not a rename of the commitment -> still fires."""
    f = advance_gate(_UNIV, [{"location": "src/missing.py"}],
                     touched_keys={"src/other.py"}, fs_exists=lambda p: False)
    assert f is not None and f.pattern_id == "gate.advance"


def test_rename_tolerance_preserves_fakeexcuse_firewall():
    """auth.py vs auth_helper.py is NOT a rename (`_helper` is not a version token) -> still fires."""
    f = advance_gate(_UNIV, [{"location": "src/auth.py"}],
                     touched_keys={"src/auth_helper.py"}, fs_exists=lambda p: False)
    assert f is not None and f.pattern_id == "gate.advance"


def test_code_span_guard_only_skips_word_INSIDE_a_span():
    """Regression: the code-span guard must be `span_start <= a < span_end` (is the done-word
    INSIDE a code span?), never `span_start > a` (is it BEFORE a span?). A flatten/mangle once
    corrupted `s <= a < e` -> `s > a < e`, which silently suppressed every genuine universal-done
    claim that happened to be followed by ANY later backtick span — a false-negative the FIRE
    set's `fe775` case catches, but only when the suite runs against the *installed* tree.

    A real prose claim followed by a LATER code span MUST still fire; a done-word genuinely
    INSIDE a span must stay inert. These two assertions together pin the comparator direction."""
    assert _advance_signal("everything is done. see `foo`.") is True   # claim before span -> fires
    assert _advance_signal("All pushed (digest `fe775`).") is True      # real-corpus FIRE shape
    assert _advance_signal("`everything is done`") is False             # word inside span -> inert
