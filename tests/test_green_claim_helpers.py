"""A1 sentinels — the shared test-runner provenance + failure-verdict signals for gate.green_claim.

These are the FP firewalls for the green-claim gate, tested against REAL runner output shapes:
  - is_test_runner: only a genuine runner command yields a 'testrun' ledger row (so a
    `cat failing.log` is never consulted).
  - is_failing_testrun: >=1 real failure, xfail-safe and 0-failed-safe.
"""
from __future__ import annotations
from makoto.substrate.io import is_test_runner, is_failing_testrun


# === is_test_runner: runner provenance =====================================

def test_runner_pytest():
    assert is_test_runner("python -m pytest tests/ -q")
    assert is_test_runner("pytest tests/test_x.py::test_y")
    assert is_test_runner("cd /repo && py.test -x")


def test_runner_ecosystems():
    assert is_test_runner("npm test")
    assert is_test_runner("yarn run test")
    assert is_test_runner("go test ./...")
    assert is_test_runner("cargo test")
    assert is_test_runner("npx jest src/")
    assert is_test_runner("vitest run")
    assert is_test_runner("tox -e py311")
    assert is_test_runner("make test")
    assert is_test_runner("python scripts/falsify.py")


def test_not_a_runner_cat_a_log():
    """the cat-a-failing-log FP firewall: displaying a log is NOT a test run -> no testrun row."""
    assert not is_test_runner("cat tests/old_failure.log")
    assert not is_test_runner("grep -r FAILED build.log")
    assert not is_test_runner("echo '=== 3 failed ==='")
    assert not is_test_runner("ls tests/")
    assert not is_test_runner("python build.py")


# === is_failing_testrun: failure verdict ===================================

def test_failure_pytest_summary():
    assert is_failing_testrun("=========== 3 failed, 678 passed in 12.31s ============")
    assert is_failing_testrun("=== 1 failed, 2 passed, 1 error in 0.4s ===")


def test_failure_markers():
    assert is_failing_testrun("FAILED tests/test_payload.py::test_intent_text_100k - assert")
    assert is_failing_testrun("ERROR tests/conftest.py - ImportError: no module named x")
    assert is_failing_testrun("=================== FAILURES ===================")
    assert is_failing_testrun("FAIL\tgithub.com/x/y\t0.123s")
    assert is_failing_testrun("Traceback (most recent call last):\n  File ...")


def test_xfail_is_not_a_failure():
    """THE xfail wall: an expected-fail run is GREEN-with-expected-fails, not a failure -> False."""
    assert not is_failing_testrun("============ 681 passed, 3 xfailed in 2.10s ============")
    assert not is_failing_testrun("=== 5 passed, 2 xfailed, 1 xpassed in 0.9s ===")


def test_clean_run_is_not_a_failure():
    assert not is_failing_testrun("============ 693 passed in 14.02s ============")
    assert not is_failing_testrun("ok  github.com/x/y  0.10s")
    assert not is_failing_testrun("Test Suites: 12 passed, 12 total")


def test_zero_failed_is_not_a_failure():
    assert not is_failing_testrun("=== 0 failed, 50 passed in 1.0s ===")


def test_benchmark_noise_is_not_a_failure():
    """a benchmark line ('Outliers: 1 Standard Deviation ...') is not a test failure -> False."""
    assert not is_failing_testrun("Outliers: 1 Standard Deviation from Mean; 1.5 IQR")
    assert not is_failing_testrun("Mean 2.0 ops/sec; 2 samples collected; no anomalies")


def test_prose_failed_does_not_match():
    """lowercase prose 'failed to connect' must not trip the case-sensitive marker (needs a count)."""
    assert not is_failing_testrun("the request failed to connect, retrying")


def test_empty_output():
    assert not is_failing_testrun("")
    assert not is_failing_testrun(None)  # type: ignore[arg-type]
