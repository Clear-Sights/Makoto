import ast

from makoto.checks.hollowTest import (
    _is_test_filename, _iter_test_functions, _is_assertion_call, _callee_chain,
    _has_skip_decorator, _is_tautology, _is_swallowed_failure, _analyze_test_function, analyze_file,
    _iter_nested_defs, _analyze_nested_test_functions, _is_skipif_call, _is_skip_call_stmt,
    _function_body_always_skip_guard, _analyze_always_skip, _analyze_module_level_always_skip,
)


def _func(src):
    return ast.parse(src).body[0]


def _call(src):
    return ast.parse(src, mode="eval").body


def _tree(src):
    return ast.parse(src)


# ---- filename scope gate ------------------------------------------------------------------------
def test_filename_gate_matches_pytest_default_discovery():
    assert _is_test_filename("tests/test_foo.py")
    assert _is_test_filename("tests/foo_test.py")
    assert _is_test_filename("test_foo.py")
    assert not _is_test_filename("tests/helpers.py")
    assert not _is_test_filename("tests/foo.py")
    assert not _is_test_filename("tests/test_foo.txt")


# ---- test-function discovery --------------------------------------------------------------------
def test_discovers_pytest_style_module_function():
    tree = _tree("def test_a():\n assert 1\n")
    names = {f.name for f in _iter_test_functions(tree)}
    assert names == {"test_a"}


def test_ignores_non_test_functions():
    tree = _tree("def helper():\n assert 1\ndef test_a():\n assert 1\n")
    names = {f.name for f in _iter_test_functions(tree)}
    assert names == {"test_a"}


def test_discovers_unittest_style_bare_test_prefix_method():
    src = ("import unittest\n"
           "class TestFoo(unittest.TestCase):\n"
           "    def testBar(self):\n"
           "        self.assertTrue(1)\n")
    tree = _tree(src)
    names = {f.name for f in _iter_test_functions(tree)}
    assert names == {"testBar"}


def test_bare_test_prefix_method_NOT_counted_without_testcase_base():
    # a class merely named Test* without a TestCase base does not license the bare-prefix relaxation
    src = ("class TestHelpers:\n"
           "    def testBar(self):\n"
           "        pass\n")
    tree = _tree(src)
    names = {f.name for f in _iter_test_functions(tree)}
    assert names == set()


def test_underscored_test_method_counts_in_any_class():
    src = ("class TestHelpers:\n"
           "    def test_bar(self):\n"
           "        assert 1\n")
    tree = _tree(src)
    names = {f.name for f in _iter_test_functions(tree)}
    assert names == {"test_bar"}


def test_async_test_function_discovered():
    tree = _tree("async def test_a():\n assert 1\n")
    names = {f.name for f in _iter_test_functions(tree)}
    assert names == {"test_a"}


# ---- assertion recognizer (generous by design) ---------------------------------------------------
def test_callee_chain_descends_through_intermediate_call():
    assert _callee_chain(_call("requests.Session().get(x)")) == "requests.Session.get"


def test_recognizes_bare_assert_style_calls():
    for src in ("self.assertTrue(x)", "self.assertEqual(a, b)", "np.testing.assert_allclose(a, b)",
                "assert_that(x)", "mock.assert_called_with(1)", "self.fail('boom')", "pytest.fail('x')",
                "pytest.raises(ValueError)"):
        assert _is_assertion_call(_call(src)), f"{src!r} should be recognized"


def test_does_not_recognize_ordinary_calls():
    for src in ("log(x)", "self.setUp()", "foo.bar(1)", "print(x)"):
        assert not _is_assertion_call(_call(src)), f"{src!r} should NOT be recognized"


# ---- skip-decorator exemption (pattern 1 only) ---------------------------------------------------
def test_skip_decorator_detected():
    f = _func("@pytest.mark.skip(reason='wip')\ndef test_a():\n pass\n")
    assert _has_skip_decorator(f)
    f2 = _func("@unittest.skipIf(True, 'x')\ndef test_a():\n pass\n")
    assert _has_skip_decorator(f2)
    f3 = _func("@pytest.mark.parametrize('x', [1])\ndef test_a(x):\n assert x\n")
    assert not _has_skip_decorator(f3)


# ---- sub-pattern 2: tautology ---------------------------------------------------------------------
def test_tautology_assert_true_literal():
    n = _func("def test_a():\n assert True\n").body[0]
    assert _is_tautology(n.test)


def test_tautology_self_equal_comparison():
    n = _func("def test_a():\n x = foo()\n assert x == x\n").body[1]
    assert _is_tautology(n.test)


def test_tautology_self_is_comparison():
    n = _func("def test_a():\n x = foo()\n assert x is x\n").body[1]
    assert _is_tautology(n.test)


def test_not_tautology_when_sides_differ():
    n = _func("def test_a():\n assert foo() == bar()\n").body[0]
    assert not _is_tautology(n.test)


def test_not_tautology_when_operator_is_not_eq_or_is():
    n = _func("def test_a():\n x = foo()\n assert x != x\n").body[1]
    assert not _is_tautology(n.test)


def test_not_tautology_multi_op_compare():
    n = _func("def test_a():\n assert 1 == 1 == 1\n").body[0]
    assert not _is_tautology(n.test)          # spec: exactly ONE operator required


# --- corpus-found FP fix: a Call can return a different object/value each evaluation, so an
# identical-looking `f() is f()` / `f() == f()` is NOT provably a tautology (real example:
# makoto's own test_gate_shape.py: `assert load_stopchecks() is load_stopchecks()`, a genuine
# memoization identity check).
def test_not_tautology_when_either_side_is_a_call():
    n = _func("def test_a():\n assert load_stopchecks() is load_stopchecks()\n").body[0]
    assert not _is_tautology(n.test)


def test_not_tautology_when_call_nested_inside_a_side():
    n = _func("def test_a():\n assert (load() or 0) == (load() or 0)\n").body[0]
    assert not _is_tautology(n.test)


# ---- sub-pattern 3: swallowed failure -------------------------------------------------------------
def test_swallowed_failure_fires_on_bare_broad_noop_except():
    f = _func("def test_a():\n try:\n  do_thing()\n except Exception:\n  pass\n")
    assert _is_swallowed_failure(f.body[0], f.body)


def test_swallowed_failure_fires_on_bare_except_colon():
    f = _func("def test_a():\n try:\n  do_thing()\n except:\n  pass\n")
    assert _is_swallowed_failure(f.body[0], f.body)


def test_not_swallowed_when_handler_type_is_narrow():
    f = _func("def test_a():\n try:\n  do_thing()\n except ValueError:\n  pass\n")
    assert not _is_swallowed_failure(f.body[0], f.body)


def test_not_swallowed_when_handler_body_is_not_noop():
    f = _func("def test_a():\n try:\n  do_thing()\n except Exception:\n  raise\n")
    assert not _is_swallowed_failure(f.body[0], f.body)


def test_not_swallowed_when_no_call_in_try_body():
    f = _func("def test_a():\n try:\n  x = 1\n except Exception:\n  pass\n")
    assert not _is_swallowed_failure(f.body[0], f.body)


def test_not_swallowed_when_assertion_survives_outside_try():
    f = _func("def test_a():\n try:\n  do_thing()\n except Exception:\n  pass\n assert True\n")
    assert not _is_swallowed_failure(f.body[0], f.body)


def test_swallowed_when_assertion_is_inside_the_compromised_try_itself():
    # the assert IS inside the try body, but the broad no-op except would itself swallow the
    # AssertionError it could raise -- so it does not count as a save.
    f = _func("def test_a():\n try:\n  do_thing()\n  assert False\n except Exception:\n  pass\n")
    assert _is_swallowed_failure(f.body[0], f.body)


def test_legitimate_narrow_except_around_real_assert_is_not_flagged():
    # a legitimate pattern: the assert can still fail the test normally since the except doesn't
    # catch AssertionError.
    f = _func("def test_a():\n try:\n  do_thing()\n  assert False\n except ValueError:\n  pass\n")
    assert not _is_swallowed_failure(f.body[0], f.body)


# ---- per-function / whole-file behavior -----------------------------------------------------------
def test_no_assertion_fires():
    f = _func("def test_a():\n x = compute()\n y = x + 1\n")
    findings = _analyze_test_function(f)
    assert any(fnd["kind"] == "no_assertion" for fnd in findings)


def test_no_assertion_silent_with_real_assert():
    f = _func("def test_a():\n x = compute()\n assert x == 1\n")
    assert _analyze_test_function(f) == []


def test_no_assertion_silent_with_recognized_assertion_call_only():
    f = _func("def test_a():\n self.assertEqual(compute(), 1)\n")
    assert _analyze_test_function(f) == []


def test_no_assertion_exempted_by_skip_decorator():
    f = _func("@pytest.mark.skip(reason='wip')\ndef test_a():\n pass\n")
    assert _analyze_test_function(f) == []


def test_no_assertion_not_exempted_by_unrelated_decorator():
    f = _func("@pytest.mark.slow\ndef test_a():\n x = 1\n")
    findings = _analyze_test_function(f)
    assert any(fnd["kind"] == "no_assertion" for fnd in findings)


def test_no_assertion_recurses_into_control_flow_blocks():
    # the only assertion lives inside a for-loop -- must still count as present (not a false fire)
    f = _func("def test_a():\n for i in range(3):\n  assert i >= 0\n")
    assert _analyze_test_function(f) == []


def test_no_assertion_does_not_recurse_into_nested_def():
    # the only assertion lives inside a nested helper def -- a separate scope, must NOT count
    f = _func("def test_a():\n def helper():\n  assert True\n helper()\n")
    findings = _analyze_test_function(f)
    assert any(fnd["kind"] == "no_assertion" for fnd in findings)


# ---- analyze_file: filename gate + syntax error + multi-finding ------------------------------------
def test_analyze_file_skips_non_test_filenames():
    src = "def test_a():\n x = 1\n"
    assert analyze_file(src, "helpers.py") == []


def test_analyze_file_skips_unparseable_files():
    assert analyze_file("def test_a(:\n bad", "test_m.py") == []


# --- corpus-found FP fix: a test's only observable check is a call to a SAME-FILE helper function
# that itself asserts (the extremely common shared-assert-helper pattern; real example: assay's
# test_forbidden_location.py `_clean(call)` wrapping `assert not verdict.fired`).
def test_helper_asserting_indirectly_is_recognized():
    src = ("def _clean(x):\n"
           "    assert not x\n"
           "def test_a():\n"
           "    _clean(compute())\n")
    findings = analyze_file(src, "test_m.py")
    assert findings == []


def test_helper_chain_transitively_recognized():
    # test_a -> _outer -> _inner (asserts). Transitive resolution must still recognize it.
    src = ("def _inner(x):\n"
           "    assert x\n"
           "def _outer(x):\n"
           "    _inner(x)\n"
           "def test_a():\n"
           "    _outer(compute())\n")
    findings = analyze_file(src, "test_m.py")
    assert findings == []


def test_helper_that_does_not_assert_does_not_suppress_the_fire():
    src = ("def _noop(x):\n"
           "    x\n"
           "def test_a():\n"
           "    _noop(compute())\n")
    findings = analyze_file(src, "test_m.py")
    assert any(f["kind"] == "no_assertion" for f in findings)


# ---- sub-pattern 4a: uncollectable nested test-shaped function -----------------------------------
def test_iter_nested_defs_finds_directly_nested_def():
    f = _func("def test_outer():\n def test_inner():\n  assert 1\n test_inner()\n")
    names = {n.name for n in _iter_nested_defs(f.body)}
    assert names == {"test_inner"}


def test_iter_nested_defs_finds_def_inside_control_flow():
    f = _func("def test_outer():\n if True:\n  def test_inner():\n   assert 1\n  test_inner()\n")
    names = {n.name for n in _iter_nested_defs(f.body)}
    assert names == {"test_inner"}


def test_iter_nested_defs_ignores_non_def_statements():
    f = _func("def test_outer():\n x = 1\n assert x\n")
    assert list(_iter_nested_defs(f.body)) == []


def test_nested_test_function_fires_when_it_has_its_own_assertion():
    f = _func("def test_outer():\n def test_inner():\n  assert compute()\n test_inner()\n")
    findings = _analyze_nested_test_functions(f)
    assert any(fnd["kind"] == "uncollectable_nested" and fnd["func"] == "test_inner" for fnd in findings)


def test_nested_non_test_named_helper_never_fires_4a():
    # a nested `def` that doesn't start with `test_` is not this sub-pattern's concern at all
    f = _func("def test_outer():\n def _helper():\n  assert compute()\n _helper()\n")
    assert _analyze_nested_test_functions(f) == []


def test_nested_test_shaped_function_without_its_own_assertion_does_not_fire_4a():
    # precision guard: an incidentally test_-named private helper with no real check inside
    f = _func("def test_outer():\n def test_inner():\n  x = 1\n test_inner()\n assert compute()\n")
    assert _analyze_nested_test_functions(f) == []


def test_nested_test_function_via_helper_assert_is_still_own_scope_only():
    # the nested function's assertion recognition uses its OWN body only (own-scope discipline);
    # a bare recognized-assertion CALL inside it still counts.
    f = _func("def test_outer():\n def test_inner():\n  self.assertTrue(compute())\n test_inner()\n")
    findings = _analyze_nested_test_functions(f)
    assert any(fnd["kind"] == "uncollectable_nested" for fnd in findings)


def test_analyze_file_fires_uncollectable_nested():
    src = "def test_outer():\n    def test_inner():\n        assert compute()\n    test_inner()\n"
    findings = analyze_file(src, "test_m.py")
    assert any(f["kind"] == "uncollectable_nested" and f["func"] == "test_inner" for f in findings)


# ---- sub-pattern 4b: permanently-true skip guard --------------------------------------------------
def test_is_skipif_call_recognizes_pytest_and_unittest_forms():
    assert _is_skipif_call(_call("pytest.mark.skipif(True, reason='x')"))
    assert _is_skipif_call(_call("unittest.skipIf(True, 'x')"))
    assert not _is_skipif_call(_call("pytest.mark.skip(reason='x')"))
    assert not _is_skipif_call(_call("pytest.mark.parametrize('x', [1])"))


def test_is_skip_call_stmt_recognizes_pytest_skip_and_skiptest_raise():
    body_skip = _func("def test_a():\n pytest.skip('x')\n").body[0]
    assert _is_skip_call_stmt(body_skip)
    body_raise = _func("def test_a():\n raise unittest.SkipTest('x')\n").body[0]
    assert _is_skip_call_stmt(body_raise)
    body_other = _func("def test_a():\n do_thing()\n").body[0]
    assert not _is_skip_call_stmt(body_other)


def test_decorator_skipif_tautology_fires():
    f = _func("@pytest.mark.skipif(True, reason='x')\ndef test_a():\n assert compute()\n")
    findings = _analyze_always_skip(f)
    assert any(fnd["kind"] == "uncollectable_always_skip" for fnd in findings)


def test_decorator_skipif_real_condition_is_silent():
    f = _func("@pytest.mark.skipif(sys.platform == 'win32', reason='x')\ndef test_a():\n assert compute()\n")
    assert _analyze_always_skip(f) == []


def test_decorator_skipif_self_compare_is_tautology():
    f = _func("@pytest.mark.skipif(FLAG == FLAG, reason='x')\ndef test_a():\n assert compute()\n")
    findings = _analyze_always_skip(f)
    assert any(fnd["kind"] == "uncollectable_always_skip" for fnd in findings)


def test_bare_argumentless_skip_decorator_is_explicitly_excluded_from_4b():
    f = _func("@pytest.mark.skip(reason='wip')\ndef test_a():\n pass\n")
    assert _analyze_always_skip(f) == []
    f2 = _func("@unittest.skip('wip')\ndef test_a():\n pass\n")
    assert _analyze_always_skip(f2) == []


def test_function_body_guard_tautology_detected():
    f = _func("def test_a():\n if True:\n  pytest.skip('x')\n assert compute()\n")
    guard = _function_body_always_skip_guard(f)
    assert guard is not None
    findings = _analyze_always_skip(f)
    assert any(fnd["kind"] == "uncollectable_always_skip" for fnd in findings)


def test_function_body_guard_real_condition_is_silent():
    f = _func("def test_a():\n if not shutil.which('foo'):\n  pytest.skip('x')\n assert compute()\n")
    assert _analyze_always_skip(f) == []


def test_function_body_guard_only_checked_as_first_statement():
    # an `if <tautology>: skip` that is NOT the first statement must not fire (deliberately shallow)
    f = _func("def test_a():\n setup()\n if True:\n  pytest.skip('x')\n assert compute()\n")
    assert _function_body_always_skip_guard(f) is None
    assert _analyze_always_skip(f) == []


def test_module_level_pytestmark_tautology_fires():
    src = ("import pytest\n"
           "pytestmark = pytest.mark.skipif(True, reason='x')\n"
           "def test_a():\n    assert compute()\n")
    tree = _tree(src)
    findings = _analyze_module_level_always_skip(tree)
    assert any(fnd["kind"] == "uncollectable_always_skip" and fnd["func"] == "<module>" for fnd in findings)


def test_module_level_pytestmark_real_condition_is_silent():
    src = ("import pytest, sys\n"
           "pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='x')\n"
           "def test_a():\n    assert compute()\n")
    assert _analyze_module_level_always_skip(_tree(src)) == []


def test_analyze_file_fires_uncollectable_always_skip():
    src = "@pytest.mark.skipif(True, reason='x')\ndef test_a():\n    assert compute()\n"
    findings = analyze_file(src, "test_m.py")
    assert any(f["kind"] == "uncollectable_always_skip" for f in findings)


def test_analyze_file_reports_multiple_kinds():
    src = ("def test_no_assert():\n"
           "    x = compute()\n"
           "def test_tautology():\n"
           "    assert True\n"
           "def test_swallowed():\n"
           "    try:\n"
           "        do_thing()\n"
           "    except Exception:\n"
           "        pass\n"
           "def test_legit():\n"
           "    assert compute() == 1\n")
    findings = analyze_file(src, "test_m.py")
    kinds = {(f["func"], f["kind"]) for f in findings}
    assert ("test_no_assert", "no_assertion") in kinds
    assert ("test_tautology", "tautology") in kinds
    assert ("test_swallowed", "swallowed_failure") in kinds
    assert not any(f["func"] == "test_legit" for f in findings)
    assert all(f["file"] == "test_m.py" for f in findings)
