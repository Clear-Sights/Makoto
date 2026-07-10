"""FP / soundness evidence harness for the hollow_test Stop gate (gate.hollow_test).

Mirrors test_liveness_fp.py's structure and rigor bar:
- H1  the corpus runner counts fires correctly,
- H2  anti-Goodhart trio PER SUB-PATTERN (known-hollow fires, known-real-test silent, near-miss silent),
- H3  the soundness sentinel set (legitimate shapes that must never fire) is ALL silent,
- H4  makoto-allow exemption, applied in the ADAPTER (not the analyzer — see stopcheck_hollow_test.py),
- H7  the pre-registered falsifier: measure() over makoto's own non-test source == 0 fires,
- H8  the real corpus-FP measurement over three real test suites (makoto/tests, assay, ventura),
      with every fire triaged by hand (see comments) rather than silently asserted to zero.
- H8b the same corpus measurement isolated to sub-patterns 4a/4b specifically (0/0/0 fires).

A FIRING soundness sentinel means a real analyzer bug. NEVER weaken a sentinel to get green.
"""
from __future__ import annotations
import ast
import subprocess
from pathlib import Path

import pytest

from makoto.checks import hollowTest as _analyzer
from tests._fpHarness import measure
from makoto.checks.hollowTest import analyze_file
from makoto.checks.hollowTest import _run as adapter_run

REPO_ROOT = Path(__file__).resolve().parent.parent.parent   # .../Skill-lab-V5


def _f(src, path="test_m.py"):
    return analyze_file(src, path)


# --- H1: corpus runner counts fires ------------------------------------------------------------
def test_harness_counts_fires_over_corpus(tmp_path):
    (tmp_path / "test_a.py").write_text("def test_a():\n x = compute()\n")       # 1: no_assertion
    (tmp_path / "test_b.py").write_text("def test_b():\n assert compute() == 1\n")  # 0: real assert
    rep = measure([str(tmp_path / "test_a.py"), str(tmp_path / "test_b.py")], _analyzer)
    assert rep["fires"] == 1
    assert len(rep["detail"]) == 1


# --- H2: anti-Goodhart trio, per sub-pattern -----------------------------------------------------
def test_no_assertion_trio():
    assert _f("def test_a():\n x = compute()\n")                                  # known-hollow
    assert _f("def test_a():\n assert compute() == 1\n") == []                    # known-real
    assert _f("def test_a():\n x = compute()\n assert x == 1\n") == []            # near-miss (real assert present)


def test_tautology_trio():
    assert _f("def test_a():\n assert True\n")                                    # known-hollow
    assert _f("def test_a():\n assert compute() == 1\n") == []                    # known-real
    assert _f("def test_a():\n x = 1\n assert x == 1\n") == []                    # near-miss: DIFFERENT exprs


def test_swallowed_failure_trio():
    assert _f("def test_a():\n try:\n  compute()\n except Exception:\n  pass\n")  # known-hollow
    assert _f("def test_a():\n try:\n  assert compute() == 1\n except ValueError:\n  pass\n") == []  # known-real
    # near-miss: broad except but a real (non-tautological) assertion survives OUTSIDE the try
    assert _f("def test_a():\n try:\n  compute()\n except Exception:\n  pass\n assert compute() == 1\n") == []


def test_uncollectable_nested_trio():
    # known-hollow: a test-shaped function nested inside another, with its own real assertion
    assert _f("def test_outer():\n def test_inner():\n  assert compute()\n test_inner()\n")
    # known-real: an ordinary top-level test, no nesting at all
    assert _f("def test_a():\n assert compute() == 1\n") == []
    # near-miss: the nested def is test_-named but has no assertion of its own (private-helper shape)
    assert _f("def test_outer():\n def test_inner():\n  x = 1\n test_inner()\n assert compute()\n") == []


def test_uncollectable_always_skip_trio():
    # known-hollow: a skipif guard whose condition is a literal tautology
    assert _f("@pytest.mark.skipif(True, reason='x')\ndef test_a():\n assert compute()\n")
    # known-real: a skipif guard gated on a genuine environment fact
    assert _f("@pytest.mark.skipif(sys.platform == 'win32', reason='x')\n"
              "def test_a():\n assert compute()\n") == []
    # near-miss: a bare, argument-less skip -- explicitly NOT this pattern (honest, transparent skip)
    assert _f("@pytest.mark.skip(reason='wip')\ndef test_a():\n pass\n") == []


# --- H3: the soundness sentinel set --------------------------------------------------------------
# Legitimate shapes that must NEVER fire. A firing sentinel means a real analyzer bug.
SOUNDNESS = {
    "real_equality_check": "def test_a():\n assert compute() == 5\n",
    "real_assertion_call": "def test_a():\n self.assertEqual(compute(), 5)\n",
    "skip_decorated_stub": "@pytest.mark.skip(reason='wip')\ndef test_a():\n pass\n",
    "unittest_skip_decorated_stub": "@unittest.skip('wip')\ndef test_a():\n pass\n",
    "assertion_inside_loop": "def test_a():\n for i in range(3):\n  assert i >= 0\n",
    "assertion_inside_try_narrow_except": (
        "def test_a():\n try:\n  assert compute()\n except ValueError:\n  pass\n"),
    "pytest_raises_context_manager": (
        "def test_a():\n with pytest.raises(ValueError):\n  compute()\n"),
    "pytest_raises_bare_call": "def test_a():\n pytest.raises(ValueError, compute)\n",
    "mock_assert_called_with": "def test_a():\n compute()\n mock_obj.assert_called_with(1)\n",
    "self_fail_on_branch": "def test_a():\n if not compute():\n  self.fail('bad')\n",
    "different_sides_equality": "def test_a():\n x = 1\n y = 2\n assert x == y\n",
    "identical_call_is_not_tautology": "def test_a():\n assert cache() is cache()\n",
    "shared_assert_helper": ("def _clean(x):\n    assert not x\n"
                              "def test_a():\n    _clean(compute())\n"),
    "unittest_bare_test_prefix_with_real_assert": (
        "import unittest\n"
        "class TestFoo(unittest.TestCase):\n"
        "    def testBar(self):\n        self.assertTrue(compute())\n"),
    "non_test_file_never_scanned": "def helper():\n x = 1\n",   # filtered at filename gate anyway
    # --- 4a sentinels ---
    "nested_helper_not_test_named": (
        "def test_a():\n    def _helper():\n        assert compute()\n    _helper()\n"
        "    assert compute()\n"),
    "nested_test_named_without_own_assertion": (
        "def test_a():\n    def test_inner():\n        x = 1\n    test_inner()\n    assert compute()\n"),
    "test_shaped_local_var_is_not_a_def": "def test_a():\n    test_inner = compute\n    assert test_inner()\n",
    # --- 4b sentinels ---
    "skipif_real_env_var_check": (
        "def test_a():\n    if not os.environ.get('X'):\n        pytest.skip('x')\n    assert compute()\n"),
    "skipif_real_shutil_which_check": (
        "@pytest.mark.skipif(not shutil.which('foo'), reason='x')\n"
        "def test_a():\n    assert compute()\n"),
    "skipif_different_sides_not_tautology": (
        "@pytest.mark.skipif(FLAG_A == FLAG_B, reason='x')\ndef test_a():\n    assert compute()\n"),
    "bare_skip_decorator_no_condition": "@pytest.mark.skip(reason='wip')\ndef test_a():\n    pass\n",
    "bare_unittest_skip_no_condition": "@unittest.skip('wip')\ndef test_a():\n    pass\n",
    "skip_guard_not_first_statement": (
        "def test_a():\n    setup()\n    if True:\n        pytest.skip('x')\n    assert compute()\n"),
    "pytestmark_real_env_condition": (
        "import pytest, sys\npytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='x')\n"
        "def test_a():\n    assert compute()\n"),
}


def test_soundness_sentinels_all_silent():
    bad = {}
    for k, v in SOUNDNESS.items():
        path = "helpers.py" if k == "non_test_file_never_scanned" else "test_m.py"
        r = _f(v, path)
        if r:
            bad[k] = r
    assert bad == {}, f"FALSE POSITIVES (real analyzer bug — fix, do NOT weaken): {list(bad)}"


# --- H4: makoto-allow exemption (applied by the ADAPTER, not the analyzer) -----------------------
class _FakeCtx:
    def __init__(self, files: dict, cwd: str):
        self.touched = tuple(files)
        self.cwd = cwd
        self._files = files

    def fs_read(self, p):
        return self._files.get(p)


def test_makoto_allow_exempts_via_adapter(tmp_path):
    p = str(tmp_path / "test_m.py")
    # no_assertion anchors its finding at the `def` line itself (no single "offending statement"
    # exists for a whole-function absence-of-assertion finding), so the annotation belongs there.
    src = "def test_a():  # makoto-allow: intentional stub\n x = compute()\n"
    ctx = _FakeCtx({p: src}, cwd=str(tmp_path))
    assert adapter_run(ctx) == []
    # control: WITHOUT the annotation the same shape fires.
    src_bare = "def test_a():\n x = compute()\n"
    ctx2 = _FakeCtx({p: src_bare}, cwd=str(tmp_path))
    findings = adapter_run(ctx2)
    assert len(findings) == 1
    assert findings[0].pattern_id == "gate.hollow_test"
    assert findings[0].level == "error"


def test_analyzer_itself_does_not_apply_makoto_allow():
    # the analyzer is unaware of the exemption -- that is the adapter's job (mission spec: the
    # escape hatch lives in stopcheck_hollow_test.py, not hollow_test.py).
    src = "def test_a():\n x = compute()  # makoto-allow: intentional stub\n"
    assert analyze_file(src, "test_m.py") != []


# --- H7: the PRE-REGISTERED FALSIFIER ------------------------------------------------------------
# Run the SAME live analyzer over makoto's own source (git-tracked *.py, tests excluded) and assert
# zero fires -- exactly like test_liveness_fp.py::test_fp_zero_on_makoto_source.
def test_fp_zero_on_makoto_nontest_source():
    from makoto.tests._repo_scope import tracked_py_files
    makoto_root = REPO_ROOT / "makoto"
    files = tracked_py_files(makoto_root)    # already root-pinned; route through the shared lister
    rep = measure([str(makoto_root / f) for f in files], _analyzer)
    assert rep["fires"] == 0, f"pre-registered falsifier FIRED — triage each candidate FP: {rep['detail']}"


# --- H8: the real corpus-FP measurement over three real test suites ------------------------------
# Every file in each corpus is scanned; every fire is triaged by hand (see the dispatcher's landing
# report for the full file:line:kind detail). Post-fix (Call-exclusion on tautology; same-file
# helper-assert resolution on pattern 1/3), the residue below is TRUE POSITIVES only:
#   makoto/tests/test_install.py:146  test_validate_predicate_modules_passes_on_current_catalog
#     -- calls a function expected not to raise, asserts nothing: a silent no-op regression would
#        pass this test. Genuine "trivially-passing" shape (known-issues.md cheat class).
#   assay: 0 fires (all 6 pre-fix fires were the `_clean`/`_reason` shared-assert-helper FP, now fixed).
#   ventura/tests/test_agent_dispatch.py:105        test_failing_spawn_never_raises_out_of_call
#     -- "doesn't raise" is the test's entire contract, no explicit assert.
#   ventura/tests/test_manifest.py:227              test_enumerate_doc_sections_h1_excluded
#     -- body is a bare `pass  # covered by ...`: an intentional but genuinely-empty stub.
#   ventura/tests/test_recompose_precautions.py:122 test_p2_hash_verify_still_rejects_tampered_content
#     -- the non-raising branch has NO assertion at all (its own comments admit this); a silent
#        regression that stops raising would pass unnoticed.
# None of these are analyzer bugs -- each is a real test that can pass regardless of the exact
# behavior it claims to pin. This corpus run is the "prove zero-FP or cut" evidence for sub-patterns
# 1-3: 0 genuine FPs survive, so all three ship.
#
# Sub-patterns 4a (uncollectable_nested) / 4b (uncollectable_always_skip) were measured SEPARATELY
# against the same three corpora (see test_corpus_fp_4a_4b_* below): 0 fires in all three. makoto's
# and assay's test suites contain zero nested test-shaped functions and zero `skipif`/`skipIf` usage
# at all. ventura has exactly one real `skipif` usage (test_anthropic_dispatch.py:375,
# test_live_smoke_one_token_round_trip, gated on `not os.environ.get("ANTHROPIC_API_KEY")`) -- a
# genuine environment fact, so `_is_tautology` correctly stays silent on it. Both 4a and 4b ship:
# real-FP evidence is 0/0/0 across all three corpora, same "prove zero-FP or cut" bar as 1-3.
def _corpus_py_files(repo_relative_root: str) -> list:
    root = REPO_ROOT / repo_relative_root
    files = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True).stdout.split()
    return [str(root / f) for f in files if f.endswith(".py")]


def test_corpus_fp_makoto_own_tests():
    if not (REPO_ROOT / "makoto").is_dir():
        pytest.skip("makoto/ sibling not present (standalone makoto checkout)")
    rep = measure(_corpus_py_files("makoto"), _analyzer)
    fires_by_func = {f["func"] for f in rep["detail"]}
    assert fires_by_func == {"test_validate_predicate_modules_passes_on_current_catalog"}, (
        f"unexpected fire set (triage new fires before changing this assertion): {rep['detail']}")


def test_corpus_fp_assay_tests():
    if not (REPO_ROOT / "assay").is_dir():
        pytest.skip("assay/ sibling not present (standalone makoto checkout)")
    rep = measure(_corpus_py_files("assay"), _analyzer)
    assert rep["fires"] == 0, f"unexpected assay fire(s) -- triage: {rep['detail']}"


def test_corpus_fp_ventura_tests():
    if not (REPO_ROOT / "ventura").is_dir():
        pytest.skip("ventura/ sibling not present (standalone makoto checkout)")
    rep = measure(_corpus_py_files("ventura"), _analyzer)
    fires_by_func = {f["func"] for f in rep["detail"]}
    assert fires_by_func == {
        "test_failing_spawn_never_raises_out_of_call",
        "test_enumerate_doc_sections_h1_excluded",
        "test_p2_hash_verify_still_rejects_tampered_content",
    }, f"unexpected fire set (triage new fires before changing this assertion): {rep['detail']}"


# --- H8b: the same real corpus-FP measurement, isolated to JUST the new 4a/4b sub-patterns --------
# (patterns 1-3's fires are already accounted for above; this filters `measure()`'s detail down to
# the two new kinds so a regression in 4a/4b specifically cannot hide inside the combined count.)
def _new_pattern_fires(repo_relative_root: str) -> list:
    rep = measure(_corpus_py_files(repo_relative_root), _analyzer)
    return [f for f in rep["detail"] if f["kind"] in ("uncollectable_nested", "uncollectable_always_skip")]


def test_corpus_fp_4a_4b_makoto_own_tests():
    assert _new_pattern_fires("makoto") == []


def test_corpus_fp_4a_4b_assay_tests():
    if not (REPO_ROOT / "assay").is_dir():
        pytest.skip("assay/ sibling not present (standalone makoto checkout)")
    assert _new_pattern_fires("assay") == []


def test_corpus_fp_4a_4b_ventura_tests():
    if not (REPO_ROOT / "ventura").is_dir():
        pytest.skip("ventura/ sibling not present (standalone makoto checkout)")
    # ventura's one real skipif usage (test_live_smoke_one_token_round_trip) is gated on a genuine
    # env-var check, not a tautology -- correctly silent. See the H8 comment block above.
    assert _new_pattern_fires("ventura") == []
