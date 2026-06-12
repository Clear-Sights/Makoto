"""Unit tests for makoto.checks — the deterministic check primitives.

Cheap, deterministic, no DB. Asserts the fakeexcuse firewall (equality, not
substring), the narrowed bash-non-empty constant, and the detectors.
"""
from makoto.checks import (
    normalize_path,
    location_match,
    quantity_match,
    subject_binds,
    detect_location,
    detect_locations,
    detect_quantity,
    bash_nonempty_violation,
)


def test_normalize_path_equality_not_substring():
    assert normalize_path("./auth.py") == normalize_path("auth.py")
    assert location_match("auth.py", ["src/auth.py", "auth.py"]) is True
    # substring collision must NOT match — the fakeexcuse firewall
    assert location_match("auth.py", ["auth_helper.py"]) is False
    assert location_match("", ["auth.py"]) is False


def test_quantity_match():
    assert quantity_match(12, n=12) is True
    assert quantity_match(13, n=12) is False
    assert quantity_match(3, lo=1, hi=5) is True
    assert quantity_match(9, lo=1, hi=5) is False
    assert quantity_match(None, n=1) is False


def test_quantity_match_lo_boundary_inclusive():
    """Line-pin (L35 CMP '<'): value EQUAL to lo must pass (boundary inclusive).
    Reddens if '<' becomes '<=' (mutant would reject value == lo)."""
    assert quantity_match(1, lo=1, hi=5) is True


def test_quantity_match_below_lo_rejected():
    """Line-pin (L36 CONST 'return False'): value below lo must be rejected.
    Reddens if the lo-block 'return False' is flipped to 'return True'."""
    assert quantity_match(0, lo=1, hi=5) is False


def test_quantity_match_single_lo_bound_passes():
    """Line-pin (L39 BOOL 'or' / L39 CMP 'is not None'): a single set bound (lo only,
    hi=None) with an in-range value must pass. Reddens if 'or' becomes 'and' (both
    bounds then required) or if 'lo is not None' becomes 'lo is None'."""
    assert quantity_match(3, lo=1) is True


def test_bash_constant_nonzero_exit_does_not_fire():
    """Line-pin (L120 BOOL 'or 0'): a non-zero exit code with empty output must NOT
    fire (exit != 0). Reddens if the 'or 0' fallback becomes 'and 0', which would
    force exit_code to 0 and falsely fire the violation."""
    assert bash_nonempty_violation(
        {"exit": 1, "stdout": "", "stderr": ""}) is False


def test_normalize_path_empty_returns_empty_string():
    """Line-pin (L14 RETURN '\"\"'): empty input returns the empty string, not None.
    A None return is observable (crashes downstream .replace callers); reddens if the
    'return \"\"' is mutated to 'return None'."""
    assert normalize_path("") == ""


def test_subject_binds_requires_equality():
    assert subject_binds("auth.py", "auth.py") is True
    assert subject_binds("auth.py", "auth_helper.py") is False
    assert subject_binds("auth.py", "fakeexcuse.txt") is False


def test_detect_location_and_quantity():
    assert detect_location("will add to `src/auth.py`") == "src/auth.py"
    assert detect_location("fix the bug") is None            # unlocated -> inert
    assert detect_quantity("add 3 tests") == (3, 3)
    assert detect_quantity("between 2 and 5") == (2, 5)
    assert detect_quantity("no number here") is None


def test_detect_location_rejects_non_path_tokens():
    """The 2026-06-01 precision fix: a version / SHA / duration / task-id / arbitrary
    backtick token is NOT a file path. These were the completion gate's 5.83% irreducible
    FP source — every one must now be unlocated (inert)."""
    for junk in ["2.0", "v1.2.0", "31.8s", "101.8s", "A.1", "5.3", "v4.1",
                 "eb1db23", "458f27f", "1ade8b0", "outline_call",
                 "`/loop until midnight`", "`lab adopt`", "`print(f'DEBUG')`", "2.2"]:
        assert detect_location(junk) is None, f"non-path falsely located: {junk!r}"


def test_detect_location_accepts_real_paths_incl_punctuation():
    """Genuine paths still resolve — relative, absolute, ~/, backticked, with a trailing
    sentence period or a :line suffix, and well-known extensionless files."""
    cases = {
        "src/auth.py": "src/auth.py",
        "see `src/auth.py` for details": "src/auth.py",
        "I wrote auth.py.": "auth.py",                          # trailing sentence period
        "error at src/auth.py:34": "src/auth.py",               # :line suffix
        "/Users/x/tmp/coldstart.md": "/Users/x/tmp/coldstart.md",
        "~/.claude/settings.json": "~/.claude/settings.json",
        "edited the Dockerfile": "Dockerfile",                  # known extensionless file
    }
    for text, expected in cases.items():
        assert detect_location(text) == expected, f"{text!r} -> {detect_location(text)!r}"


def test_detect_locations_yields_all_paths_in_order():
    locs = [loc for loc, _a, _b in detect_locations("wrote a.py then updated b/c.md")]
    assert locs == ["a.py", "b/c.md"]


def test_detect_quantity_speedup_and_decimal():
    # Nx / N× / decimal speedups are the domain's most common quantity shape.
    assert detect_quantity("achieved 2x speedup") == (2, 2)
    assert detect_quantity("a 2.4x improvement") == (2.4, 2.4)
    assert detect_quantity("2× faster than baseline") == (2, 2)
    assert detect_quantity("between 2 and 5") == (2, 5)


def test_bash_constant_honors_nooutputexpected():
    assert bash_nonempty_violation(
        {"stdout": "", "stderr": "", "exitCode": 0, "noOutputExpected": False}) is True
    # mkdir/touch: the harness marks empty output as expected -> never fire
    assert bash_nonempty_violation(
        {"stdout": "", "stderr": "", "exitCode": 0, "noOutputExpected": True}) is False
    assert bash_nonempty_violation(
        {"stdout": "ok", "exitCode": 0, "noOutputExpected": False}) is False
    assert bash_nonempty_violation("not a dict") is False


def test_quantity_match_single_hi_bound_passes():
    # L39 `lo is not None or hi is not None` (hi operand): an upper-only bound matches;
    # the `hi is None` mutant returns False and misses the hi-only quantity claim.
    assert quantity_match(3, hi=5) is True
