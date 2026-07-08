"""FP / soundness evidence harness for the liveness Stop gate (gate.liveness; Phase 2, H1-H7).

Every test here is a re-runnable artifact of the analyzer's false-positive behaviour:
- H1  the corpus runner counts fires correctly,
- H2  anti-Goodhart trio (known-illusory fires, known-live silent, near-miss silent),
- H3  the soundness sentinel set (plan's 7 + the 3 review-found classes) is ALL silent,
- H4  makoto-allow file-driver exemption,
- H5  teeth: an UNSOUND variant (purity guard dropped) MUST false-positive,
- H6  sole-killer: the real analyzer is silent on operator_overload because is_pure rejects it,
- H7  the pre-registered falsifier: measure() over makoto's own source == 0 fires.

A FIRING soundness sentinel means a real analyzer bug. NEVER weaken a sentinel to get green.
"""
from __future__ import annotations
import ast

from makoto.checks._fpHarness import measure
from makoto.checks.deadPureStatement import (
    illusory_statements, analyze_file, live_locals, _assigned_name)


def _f(src):
    return ast.parse(src).body[0]


# --- H1: corpus runner counts fires ------------------------------------------------------------
def test_harness_counts_fires_over_corpus(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n d = 1+1\n return 0\n")   # 1 illusory
    (tmp_path / "b.py").write_text("def g(c):\n r = c+1\n return 0\n")  # 0 (impure operand)
    rep = measure([str(tmp_path / "a.py"), str(tmp_path / "b.py")])
    assert rep["fires"] == 1
    assert len(rep["detail"]) == 1


# --- H2: anti-Goodhart trio --------------------------------------------------------------------
# A detector that flags everything passes the known-illusory test and a detector that flags nothing
# passes the known-live/near-miss tests; only the THREE together pin a real discriminator.
KNOWN_ILLUSORY = "def fn():\n d = 1 + 1\n return 0"
KNOWN_LIVE     = "def fn():\n a = 1\n return a"
NEAR_MISS      = "def fn():\n a = 1\n b = a + 1\n return b"   # pure but its value DOES reach the return


def test_known_illusory_fires():
    assert illusory_statements(_f(KNOWN_ILLUSORY))


def test_known_live_silent():
    assert illusory_statements(_f(KNOWN_LIVE)) == []


def test_near_miss_silent():
    assert illusory_statements(_f(NEAR_MISS)) == []


# --- H3: the soundness sentinel set, EXPANDED --------------------------------------------------
# The plan's 7 known-LIVE patterns PLUS the 3 false-positive classes found + fixed in analyzer review.
# Every one must be SILENT; a firing sentinel means a real analyzer FP bug (do NOT weaken the sentinel).
SOUNDNESS = {
    # --- plan's 7 ---
    "operator_overload": "def fn(c):\n r = c + 1\n return 0",            # c.__add__ may have an effect
    "closure_capture":   "def o():\n r = 1\n def i():\n  return r\n return i",
    "nonlocal_write":    "def o():\n s = 0\n def i():\n  nonlocal s\n  s = s + 1\n return i",
    "walrus_leak":       "def fn():\n [ (y := j) for j in range(3) ]\n return y",
    "try_except":        "def fn():\n try:\n  x = 1\n except Exception:\n  return x\n return 0",
    "property_read":     "def fn(o):\n v = o.val\n return 0",            # o.val may be a property w/ effect
    "aug_subscript":     "def fn(o):\n o[0] += 1\n return 0",            # __setitem__/__iadd__ escape
    # --- the 3 review-found FP classes (must stay locked) ---
    # 1. builtin-call on an UNKNOWN-typed operand: len/min/sum/sorted/abs/str/bool/round all dispatch to
    #    a user dunder (__len__/__lt__/__add__/__abs__/...), so they are NOT pure on a bare parameter.
    "builtin_on_object": ("def fn(o):\n a = len(o)\n b = min([o, o])\n c = sum(o)\n d = sorted(o)\n"
                          " e = abs(o)\n g = str(o)\n h = bool(o)\n k = round(o)\n return 0"),
    # 2. docstrings / bare literals: a bare string is __doc__, `...` is a stub, a bare number is a no-op
    #    — none is computation-shaped work, so none is illusory.
    "docstring":         "def fn():\n \"doc\"\n ...\n 42\n return 0",
    # 3. control-flow-only liveness: a flag/counter read ONLY in a while/if/for condition or iterable
    #    genuinely steers execution, so it is live even though its value never reaches a return. (Note:
    #    the counter IS read in the loop test `n < 3`; a counter assigned but read in NO condition would
    #    be a genuine dead counter — a TRUE positive, not this class.)
    "control_flow_flag": ("def fn():\n ok = True\n n = 0\n while ok and n < 3:\n  ok = False\n"
                          "  n = n + 1\n return 0"),
}


def test_soundness_sentinels_all_silent():
    bad = {k: [s.lineno for s in illusory_statements(_f(v))] for k, v in SOUNDNESS.items()}
    assert all(v == [] for v in bad.values()), \
        f"FALSE POSITIVES (real analyzer bug — fix L, do NOT weaken): {[k for k, v in bad.items() if v]}"


# --- H4: makoto-allow file-driver exemption ----------------------------------------------------
def test_makoto_allow_annotation_exempts():
    # An on-the-record `makoto-allow` on the illusory line overrides the fire at the file driver:
    # `d = 1 + 1` IS illusory, but the auditable rationale exempts it (analyze_file honors it).
    src = "def fn():\n d = 1 + 1  # makoto-allow: intentional\n return 0\n"
    assert analyze_file(src, "m.py") == []
    # control: WITHOUT the annotation the same line fires (the exemption is doing real work).
    src_bare = "def fn():\n d = 1 + 1\n return 0\n"
    assert analyze_file(src_bare, "m.py") != []


# --- H5: teeth — an UNSOUND variant MUST false-positive on the soundness corpus -----------------
def _unsound(func):
    """The analyzer with its PURITY GUARD DROPPED: flag every result-unused assign as illusory,
    ignoring whether the RHS could dispatch to a user dunder. A correct (sound) analyzer must NOT
    behave like this; if the soundness corpus could not redden it, the corpus would have no teeth."""
    live = live_locals(func)
    return [s for s in func.body if _assigned_name(s) and _assigned_name(s) not in live]


def test_teeth_unsound_analyzer_false_positives():
    # On operator_overload the unsound variant WRONGLY flags `r = c + 1` (c.__add__ may have an effect).
    flagged = _unsound(_f(SOUNDNESS["operator_overload"]))
    assert flagged, "teeth: an unsound analyzer must false-positive (the harness has teeth)"
    # And it reddens MORE of the soundness corpus than the real analyzer does (the corpus discriminates).
    unsound_fp = [k for k, v in SOUNDNESS.items() if _unsound(_f(v))]
    real_fp = [k for k, v in SOUNDNESS.items() if illusory_statements(_f(v))]
    assert real_fp == [], f"real analyzer FP'd (bug): {real_fp}"
    assert set(unsound_fp) > set(real_fp), "the unsound variant must FP where the real analyzer does not"


# --- H6: sole-killer — the real analyzer is silent BECAUSE is_pure rejects the overloaded operand -
def test_sole_killer_purity_guard():
    # Same input the unsound variant FP'd on: the real analyzer is silent, and the SOLE reason is the
    # purity guard (is_pure -> _builtin_typed rejects bare param `c`). Removing it reddens (proved above).
    assert illusory_statements(_f(SOUNDNESS["operator_overload"])) == []


# --- H7: the PRE-REGISTERED FALSIFIER ----------------------------------------------------------
# Run the SAME live analyzer over makoto's own source (git-tracked *.py, tests excluded) and assert
# zero fires. Pre-registered falsifier: if this is > 0, every fire is triaged — a genuine dead pure
# statement is a TRUE positive to RECORD; a live/impure fire is an FP and the analyzer regressed
# (STOP + report, do NOT weaken this test).
#
# FPReport (measured, neutral — provenance per CLAUDE.md operational rule 1):
#   code SHA   : 628bc5f (this commit adds the test; corpus = its parent's tree + fp_harness.py)
#   model      : claude-opus-4-8
#   corpus     : `git ls-files "*.py"` minus tests/  (82 files at measurement)
#   measurement: fires == 0  (no candidate FPs to triage; pre-registered falsifier did NOT fire)
def test_fp_zero_on_makoto_source():
    from makoto.tests._repo_scope import tracked_py_files
    rep = measure(tracked_py_files())        # scope pinned to makoto/, cwd-independent
    assert rep["fires"] == 0, f"pre-registered falsifier FIRED — triage each candidate FP: {rep['detail']}"


# --- H8: the two corpus FP classes (precheck.liveness shelved at corpus_fp=3) -------------------
# Class 1 — TUPLE-UNPACK LOOP READ: a name read via the RHS of a tuple-unpack assignment whose
#   unpacked targets ARE live is itself live (its value reaches the live targets). live_locals
#   missed it because a tuple-unpack assign has no single _assigned_name, so its RHS reads were
#   never propagated. Corpus: cells_frame.py 'sample_patterns', cells_plan.py (same shape).
# Class 2 — ANNASSIGN-NONE THEN RE-RAISED: `last_exc: Exception | None = None` later re-assigned
#   and read inside a `raise` is live; `raise` was never a liveness seed, so the None-init was
#   flagged dead. Corpus: paid_client.py 'last_exc'.
# Each repro is the minimal faithful shape of the real corpus fire; both must go from RED -> GREEN.

# Faithful minimal of cells_frame.py frame_assess_dont: sample_patterns read via a tuple-unpack
# whose targets (tool/pattern) are used; the list-init must NOT be flagged dead.
TUPLE_UNPACK_LOOP_READ = (
    "def fn(n):\n sample_patterns = [(1, 2), (3, 4)]\n out = []\n"
    " for i in range(n):\n  tool, pattern = sample_patterns[i % 2]\n  out.append(tool + pattern)\n"
    " return out")

# Faithful minimal of paid_client.py complete: last_exc None-init, reassigned in except, re-raised.
ANNASSIGN_NONE_THEN_RERAISE = (
    "def fn(n):\n last_exc: Exception | None = None\n for i in range(n):\n  try:\n"
    "   return do(i)\n  except Exception as e:\n   last_exc = e\n raise RuntimeError(last_exc)")

# FN guard: a genuinely-dead tuple-unpack feeder must STILL fire. `x = 1 + 1` is pure-dead, then
# unpacked into UNUSED targets — making tuple RHS unconditionally live would hide x (a NEW FN);
# the fix seeds RHS reads only when an unpacked target is live, so x stays flagged here.
DEAD_FEEDS_UNUSED_UNPACK = (
    "def fn():\n x = 1 + 1\n a, b = x, 0\n return 0")


def test_tuple_unpack_loop_read_is_live():
    # RED before fix: sample_patterns wrongly flagged dead. GREEN after: silent.
    assert illusory_statements(_f(TUPLE_UNPACK_LOOP_READ)) == [], \
        "FP: sample_patterns is read by a live tuple-unpack and must not be flagged dead"
    assert "sample_patterns" in live_locals(_f(TUPLE_UNPACK_LOOP_READ))


def test_annassign_none_then_reraise_is_live():
    # RED before fix: last_exc None-init wrongly flagged dead. GREEN after: silent.
    assert illusory_statements(_f(ANNASSIGN_NONE_THEN_RERAISE)) == [], \
        "FP: last_exc is re-raised and must not be flagged dead"
    assert "last_exc" in live_locals(_f(ANNASSIGN_NONE_THEN_RERAISE))


def test_dead_feeder_of_unused_unpack_still_fires():
    # FN guard: x is genuinely dead (feeds only unused unpack targets) -> must STILL fire. The
    # load-bearing assertion is that the live_locals propagation fix did NOT over-suppress x:
    # because the unpack targets (a, b) are dead, x's RHS reads are never seeded live, so x stays
    # flagged. (Line 3 `a, b = x, 0` is ALSO a genuine dead pure unpack — a correct TP newly caught
    # by the unpack-FN branch — so it fires too; both are real dead pure statements.)
    lines = {s.lineno for s in illusory_statements(_f(DEAD_FEEDS_UNUSED_UNPACK))}
    assert 2 in lines, f"FN regression: a genuinely-dead pure feeder must still fire, got {lines}"
    assert lines == {2, 3}, f"the dead unpack on line 3 is also a TP; got {lines}"


# --- H9: ast.Match subject/guard is a CONSUMING position (FP fix) -------------------------------
# A local read ONLY by a `match` subject (or a case guard) genuinely steers which arm runs, exactly
# like an `if`/`while` test — but live_locals never seeded ast.Match, so it was flagged dead. The
# same code with `if status == 2:` was correctly silent, the match form was an FP.
MATCH_SUBJECT_LIVE = (
    "def f():\n status = 1 + 1\n match status:\n  case 2:\n   return True\n return False")
IF_SUBJECT_LIVE = (
    "def f():\n status = 1 + 1\n if status == 2:\n  return True\n return False")
# Descent guard: a dead pure assign INSIDE a case body is still dead -> must fire.
DEAD_IN_CASE_BODY = (
    "def f(x):\n match x:\n  case 2:\n   d = 1 + 1\n   return True\n return False")


def test_match_subject_read_is_live():
    # RED before fix: status flagged dead (subject not seeded). GREEN after: silent, matching `if`.
    assert illusory_statements(_f(MATCH_SUBJECT_LIVE)) == [], \
        "FP: a local consumed by a match subject must not be flagged dead"
    assert illusory_statements(_f(IF_SUBJECT_LIVE)) == [], "control: the `if` form is silent"
    assert "status" in live_locals(_f(MATCH_SUBJECT_LIVE))


def test_dead_pure_inside_match_case_still_fires():
    # _scan must descend into case bodies: a dead pure assign in an arm is a TRUE positive.
    lines = {s.lineno for s in illusory_statements(_f(DEAD_IN_CASE_BODY))}
    assert lines == {4}, f"a dead pure assign inside a match case must fire, got {lines}"


# --- H10: dead TUPLE/LIST/CHAINED-target unpack where EVERY name is dead (FN fix) ---------------
# A dead pure unpack whose every bound name is dead was never flagged (no single _assigned_name).
DEAD_TUPLE_UNPACK   = "def f():\n a, b = 1, 2\n return 0"
DEAD_ONE_TUPLE      = "def f():\n (x,) = (1 + 2,)\n return 0"
DEAD_CHAINED        = "def f():\n a = b = 5\n return 0"
DEAD_LIST_UNPACK    = "def f():\n [a, b] = [1, 2]\n return 0"
# GREEN guards: any one live/captured/impure/escaping target keeps the whole binding live.
LIVE_TUPLE_ONE_USED = "def f():\n a, b = 1, 2\n return a"            # a live
IMPURE_UNPACK       = "def f():\n a, b = g()\n return a"             # impure RHS (and a live)
STAR_USED           = "def f(xs):\n a, *b = xs\n return b"           # b live
SWAP_USED           = "def f(p, q):\n a, b = p, q\n a, b = b, a\n return a + b"
NESTED_C_LIVE       = "def f():\n (a, (b, c)) = (1, (2, 3))\n return c"
CHAINED_A_LIVE      = "def f():\n a = b = 5\n return a"
CLOSURE_CAP_UNPACK  = "def o():\n a, b = 1, 2\n def i():\n  return a\n return i"
LAMBDA_CAP_UNPACK   = "def o():\n a, b = 1, 2\n return lambda: a"
ATTR_TARGET_UNPACK  = "def f(o):\n o.x, o.y = 1, 2\n return 0"       # store escapes (is_effect)
SUB_TARGET_UNPACK   = "def f(o):\n o[0], o[1] = 1, 2\n return 0"     # store escapes (is_effect)
GLOBAL_READ_RHS     = "def f():\n a, b = G, 1\n return 0"            # global read -> impure RHS


def test_dead_tuple_unpack_fires():
    assert {s.lineno for s in illusory_statements(_f(DEAD_TUPLE_UNPACK))} == {2}, \
        "FN: a, b = 1, 2 with both names dead must fire"


def test_dead_one_tuple_unpack_fires():
    assert {s.lineno for s in illusory_statements(_f(DEAD_ONE_TUPLE))} == {2}, \
        "FN: (x,) = (1+2,) with x dead must fire (1-tuple bypass)"


def test_dead_chained_target_fires():
    assert {s.lineno for s in illusory_statements(_f(DEAD_CHAINED))} == {2}, \
        "FN: a = b = 5 with both names dead must fire"


def test_dead_list_unpack_fires():
    assert {s.lineno for s in illusory_statements(_f(DEAD_LIST_UNPACK))} == {2}, \
        "FN: [a, b] = [1, 2] with both names dead must fire"


def test_unpack_green_guards_all_silent():
    guards = {
        "live_tuple_one_used": LIVE_TUPLE_ONE_USED, "impure_unpack": IMPURE_UNPACK,
        "star_used": STAR_USED, "swap_used": SWAP_USED, "nested_c_live": NESTED_C_LIVE,
        "chained_a_live": CHAINED_A_LIVE, "closure_cap": CLOSURE_CAP_UNPACK,
        "lambda_cap": LAMBDA_CAP_UNPACK, "attr_target": ATTR_TARGET_UNPACK,
        "sub_target": SUB_TARGET_UNPACK, "global_read_rhs": GLOBAL_READ_RHS,
    }
    bad = {k: [s.lineno for s in illusory_statements(_f(v))] for k, v in guards.items()}
    assert all(v == [] for v in bad.values()), \
        f"unpack widening over-fired (FP): {[k for k, v in bad.items() if v]}"
