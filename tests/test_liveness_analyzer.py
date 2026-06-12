import ast


def _expr(src):
    return ast.parse(src, mode="eval").body


def _stmt(src):
    return ast.parse(src).body[0]


def _func(src):
    return ast.parse(src).body[0]


# ---- L1: _builtin_typed ----
def test_builtin_typed_constants_and_containers():
    from makoto.stopchecks.liveness import _builtin_typed
    assert _builtin_typed(_expr("1"))
    assert _builtin_typed(_expr("[1, 2, 3]"))
    assert _builtin_typed(_expr("(1, 'a')"))
    assert _builtin_typed(_expr("{1: 2}"))
    assert _builtin_typed(_expr("len([1,2])"))      # whitelisted builtin call on literals
    assert not _builtin_typed(_expr("x"))           # a Name is not provably builtin-typed
    assert not _builtin_typed(_expr("o.attr"))
    assert not _builtin_typed(_expr("[x]"))         # element not provably builtin-typed


# ---- L2: is_pure ----
def test_literal_and_local_and_builtin_typed_op_are_pure():
    from makoto.stopchecks.liveness import is_pure
    assert is_pure(_expr("1 + 2"), {"x"})
    assert is_pure(_expr("x"), {"x"})                       # local read
    assert is_pure(_expr("len([1,2,3])"), set())            # whitelisted builtin on literals


def test_unknown_call_attr_subscript_await_are_impure():
    from makoto.stopchecks.liveness import is_pure
    assert not is_pure(_expr("f(x)"), {"x"})                # unknown call
    assert not is_pure(_expr("o.attr"), {"o"})              # attribute -> possible descriptor
    assert not is_pure(_expr("o[i]"), {"o", "i"})           # subscript -> __getitem__
    assert not is_pure(ast.parse("async def g():\n await h()").body[0].body[0].value, set())


def test_operator_on_unknown_typed_operand_is_impure():
    from makoto.stopchecks.liveness import is_pure
    # c is a local but NOT provably builtin-typed -> '+' may dispatch to __add__ (the audit's hole)
    assert not is_pure(_expr("c + 1"), {"c"})


def test_nonlocal_read_is_not_pure():
    from makoto.stopchecks.liveness import is_pure
    assert not is_pure(_expr("GLOBAL_THING"), set())        # name not in locals


# ---- L3: is_effect ----
def test_unknown_call_stmt_is_effect():
    from makoto.stopchecks.liveness import is_effect
    assert is_effect(_stmt("f(x)"), {"x"}, set())


def test_global_nonlocal_assign_is_effect():
    from makoto.stopchecks.liveness import is_effect
    assert is_effect(_stmt("g = 1"), set(), {"g"})          # g declared global/nonlocal


def test_attr_subscript_store_is_effect():
    from makoto.stopchecks.liveness import is_effect
    assert is_effect(_stmt("o.a = 1"), {"o"}, set())
    assert is_effect(_stmt("o[0] = 1"), {"o"}, set())
    assert is_effect(_stmt("o[0] += 1"), {"o"}, set())


def test_pure_local_assign_is_not_effect():
    from makoto.stopchecks.liveness import is_effect
    assert not is_effect(_stmt("y = 1 + 2"), set(), set())


# ---- L4: _escaping_names ----
def test_escaping_names_collects_global_and_nonlocal():
    from makoto.stopchecks.liveness import _escaping_names
    f = _func("def fn():\n global g\n nonlocal n\n g = 1\n")
    assert _escaping_names(f) == {"g", "n"}


def test_escaping_names_empty_when_none_declared():
    from makoto.stopchecks.liveness import _escaping_names
    f = _func("def fn():\n a = 1\n return a")
    assert _escaping_names(f) == set()


# ---- L5: captured_locals ----
def test_closure_capture_is_collected():
    from makoto.stopchecks.liveness import captured_locals
    f = _func("def outer():\n r = expensive()\n def inner():\n  return r\n return inner")
    assert "r" in captured_locals(f)


def test_walrus_leak_is_collected():
    from makoto.stopchecks.liveness import captured_locals
    f = _func("def fn():\n [ (y := i) for i in range(3) ]\n return y")
    assert "y" in captured_locals(f)


def test_plain_local_not_captured():
    from makoto.stopchecks.liveness import captured_locals
    f = _func("def fn():\n a = 1\n return a")
    assert "a" not in captured_locals(f)


# ---- L6: _names_read / _assigned_name ----
def test_names_read_collects_loads_only():
    from makoto.stopchecks.liveness import _names_read
    assert _names_read(_expr("a + b")) == {"a", "b"}
    assert _names_read(_stmt("x = a + b")) == {"a", "b"}    # x is Store, not read


def test_assigned_name_single_target():
    from makoto.stopchecks.liveness import _assigned_name
    assert _assigned_name(_stmt("x = 1")) == "x"
    assert _assigned_name(_stmt("x: int = 1")) == "x"
    assert _assigned_name(_stmt("x += 1")) == "x"
    assert _assigned_name(_stmt("x, y = 1, 2")) is None     # tuple target -> not a single name
    assert _assigned_name(_stmt("o.a = 1")) is None         # attribute target -> not a plain name


# ---- L7: live_locals ----
def test_value_reaching_return_is_live():
    from makoto.stopchecks.liveness import live_locals
    f = _func("def fn():\n a = 1\n b = a + 1\n return b")
    assert {"a", "b"} <= live_locals(f)


def test_dead_chain_is_not_live():
    from makoto.stopchecks.liveness import live_locals
    # a feeds b feeds c, but c is never returned/used -> none live
    f = _func("def fn():\n a = 1\n b = a + 1\n c = b + 1\n return 0")
    assert live_locals(f) == set()


def test_try_body_assignment_conservatively_live():
    from makoto.stopchecks.liveness import live_locals
    f = _func("def fn():\n try:\n  x = risky()\n except Exception:\n  return x\n return 0")
    assert "x" in live_locals(f)


# ---- L8: illusory_statements + _scan (spec cases) ----
def test_flags_dead_pure_chain():
    from makoto.stopchecks.liveness import illusory_statements
    f = _func("def fn():\n a = 1\n b = a + 1\n c = b + 1\n return 0")
    lines = {s.lineno for s in illusory_statements(f)}
    assert lines == {2, 3, 4}                                # all three pure dead stmts


def test_sideeffect_is_live_not_flagged():
    from makoto.stopchecks.liveness import illusory_statements
    f = _func("def fn():\n x = log(1)\n return 0")           # log() is an effect
    assert illusory_statements(f) == []


def test_operator_overload_operand_not_flagged():
    from makoto.stopchecks.liveness import illusory_statements
    f = _func("def fn(c):\n r = c + 1\n return 0")           # c+1 may dispatch __add__ -> impure
    assert illusory_statements(f) == []


def test_nested_capture_not_flagged():
    from makoto.stopchecks.liveness import illusory_statements
    f = _func("def outer():\n r = 1\n def inner():\n  return r\n return inner")
    assert illusory_statements(f) == []


def test_exception_dataflow_not_flagged():
    from makoto.stopchecks.liveness import illusory_statements
    f = _func("def fn():\n try:\n  x = 1\n except Exception:\n  return x\n return 0")
    assert illusory_statements(f) == []


def test_flags_waste_inside_for_loop():                      # block-closure model: recurse into blocks
    from makoto.stopchecks.liveness import illusory_statements
    f = _func("def fn():\n for i in range(3):\n  d = 1 + 1\n return 0")
    assert {s.lineno for s in illusory_statements(f)} == {3}


def test_nested_function_not_scanned_as_parent_block():
    from makoto.stopchecks.liveness import illusory_statements
    f = _func("def outer():\n def inner():\n  d = 1 + 1\n  return 0\n return inner")
    # inner's body is a SEPARATE scope (analyzed independently), not scanned as outer's block
    assert illusory_statements(f) == []


# ---- W1: analyze_file ----
def test_analyze_file_collects_per_function():
    from makoto.stopchecks.liveness import analyze_file
    src = "def a():\n d = 1+1\n return 0\ndef b():\n return 1\n"
    findings = analyze_file(src, "m.py")
    assert any(f["file"] == "m.py" and f["line"] == 2 for f in findings)


def test_syntaxerror_file_skipped():
    from makoto.stopchecks.liveness import analyze_file
    assert analyze_file("def a(:\n bad", "m.py") == []      # no crash, no fire


def test_makoto_allow_exempts():
    from makoto.stopchecks.liveness import analyze_file
    src = "def a():\n d = 1+1  # makoto-allow: intentional placeholder\n return 0\n"
    assert analyze_file(src, "m.py") == []                  # on-the-record override, not flagged


# --- soundness sentinel: builtin call on an unknown-typed operand (review-fix 2026-06-07) ---
def test_builtin_call_on_unknown_operand_is_impure():
    """len/min/sum/sorted/abs/str/bool/round dispatch to USER dunders (__len__/__lt__/__add__/...)
    on a non-builtin operand -> possibly side-effecting -> NOT pure. Only a provably builtin-typed
    operand keeps them pure."""
    from makoto.stopchecks.liveness import is_pure
    for src in ("len(o)", "min([a,b])", "sum(items)", "sorted(it)", "abs(o)",
                "str(o)", "bool(o)", "round(o)"):
        assert not is_pure(_expr(src), {"o", "a", "b", "items", "it"}), f"{src} must be impure"
    assert is_pure(_expr("len([1,2,3])"), set())          # builtin-typed operand stays pure


def test_dead_builtin_on_object_not_flagged():
    from makoto.stopchecks.liveness import illusory_statements
    for src in ("def fn(o):\n x = len(o)\n return 0",
                "def fn(items):\n t = sum(items)\n return 0",
                "def fn(a,b):\n m = min([a,b])\n return 0"):
        assert illusory_statements(_func(src)) == [], f"FALSE POSITIVE on: {src!r}"


# --- soundness sentinels: docstrings + control-flow liveness (review-fixes #2/#3, 2026-06-07) ---
def test_docstring_and_bare_literal_not_flagged():
    from makoto.stopchecks.liveness import illusory_statements
    assert illusory_statements(_func('def fn():\n "documentation"\n return 1')) == []
    assert illusory_statements(_func('def fn():\n ...\n return 1')) == []          # stub placeholder
    # a docstring must not suppress a REAL dead statement next to it
    lines = {s.lineno for s in illusory_statements(_func('def fn():\n "doc"\n d = 1 + 1\n return 0'))}
    assert lines == {3}


def test_value_read_only_in_control_flow_is_live():
    from makoto.stopchecks.liveness import illusory_statements
    # flag read by a while test
    assert illusory_statements(_func('def fn():\n ok = True\n while ok:\n  ok = False\n return 0')) == []
    # value read by an if test
    assert illusory_statements(_func('def fn(x):\n big = x > 5\n if big:\n  return 1\n return 0')) == []
    # counter read by a return compare, incremented in a loop
    assert illusory_statements(_func('def fn(xs):\n n = 0\n for x in xs:\n  n += 1\n return n == 0')) == []
    # iterable read by a for
    assert illusory_statements(_func('def fn(xs):\n items = list(xs)\n for i in items:\n  print(i)\n return 0')) == []
