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
import subprocess

from makoto.stopchecks.fp_harness import measure
from makoto.stopchecks.liveness import (
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
    files = subprocess.run(["git", "ls-files", "*.py"],
                           capture_output=True, text=True).stdout.split()
    rep = measure([f for f in files if not f.startswith("tests/")])
    assert rep["fires"] == 0, f"pre-registered falsifier FIRED — triage each candidate FP: {rep['detail']}"
