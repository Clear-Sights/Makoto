r"""is_failing_testrun must see through ANSI SGR color codes.

Measured on the honest corpus (novita/agentic_code_dataset_22): vitest colorizes its summary as
`...| \x1b[31m2 failed\x1b[39m`. The SGR terminator `m` of `\x1b[31m` is a WORD char that abuts the
digit, so `\b[1-9]\d*\s+failed` has no word boundary before the count and silently misses a REAL
failing run — 18 such failures slipped past gate.green_claim's resolver. Stripping ANSI restores
` 2 failed` and the EXISTING tuned regex matches. FP-safe: stripping color cannot manufacture a
failure, and the `[1-9]\d*` / xfail word-boundary guards are untouched.
"""
from makoto.lib.io import is_failing_testrun

ESC = "\x1b"


def test_ansi_vitest_failure_is_detected():
    # The real corpus byte form: `m` abuts the digit, killing the \b before `N failed`.
    out = (f" Test Files{ESC}[2m | {ESC}[22m{ESC}[31m1 failed{ESC}[39m (1)\n"
           f" Tests{ESC}[2m | {ESC}[22m{ESC}[31m2 failed{ESC}[39m | {ESC}[32m19 passed{ESC}[39m (21)")
    assert is_failing_testrun(out) is True


def test_ansi_passing_run_stays_silent():
    out = (f" Test Files {ESC}[32m1 passed{ESC}[39m (1)\n"
           f" Tests {ESC}[32m23 passed{ESC}[39m (23)")
    assert is_failing_testrun(out) is False


def test_ansi_xfail_run_stays_silent():
    # xfail-safety must survive the strip: '2 xfailed' must NOT read as '2 ... failed'.
    out = f" Tests {ESC}[33m2 xfailed{ESC}[39m | {ESC}[32m19 passed{ESC}[39m (21)"
    assert is_failing_testrun(out) is False


def test_plain_failure_still_detected_unchanged():
    # No ANSI -> behaviour identical to before.
    assert is_failing_testrun("===== 2 failed, 5 passed in 1.2s =====") is True
    assert is_failing_testrun("===== 7 passed in 1.2s =====") is False
