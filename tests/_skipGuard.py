"""The suite may not report green on tests it never ran.

A skipped test is NOT-EVALUABLE, never a pass, and this package's own `tests/mint_event_gold.py`
states the law it belongs to: *"trajectory gold silently counted NOT-EVALUABLE events as passes."*
The same counting error had been running against the suite itself. Five tests -- the `assay/` and
`ventura/` corpus-FP arms and the assay coverage-parity module -- were conditioned on sibling
directories of a monorepo this package no longer lives in, so they skipped on every run in this
repository's history while `1904 passed, 5 skipped` read as a clean suite.

WHY THIS CANNOT BE A SOURCE-READING CHECK. `makoto` ships a detector for exactly this shape:
`hollowTest` fires on a test that skips itself. It could not fire on these, because
`(REPO_ROOT / "assay").is_dir()` is a runtime condition, not a syntactic tautology -- true in the
monorepo the code was written in, permanently false everywhere it has run since. No reading of the
source settles whether a path will exist; only running does. So the observation is made where the
answer lives: at the end of the session, over what actually happened.

A genuinely conditional test is still expressible -- assert the condition, or parametrize it away.
What is refused is an absence that the summary line counts as success.
"""
from __future__ import annotations

_SKIPPED: list[str] = []


def pytest_runtest_logreport(report):
    """Collect every skip, from BOTH phases.

    The distinction is the whole check: a `skipif` decorator or a module-level skip reports at
    SETUP, while a `pytest.skip()` inside a test body reports at CALL. Watching setup alone was the
    first version of this guard, and it stayed silent on a planted body-skip -- which is four of
    the five skips it was written to catch, including every sibling-corpus arm. It was seen failing
    before it was believed, which is why both phases are counted here.

    `wasxfail` is excluded because pytest reports an xfailed test as skipped: an xfail is a
    recorded, named expectation that RAN, not a measurement that never happened.
    """
    if report.skipped and not hasattr(report, "wasxfail"):
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        _SKIPPED.append(f"{report.nodeid}: {reason}")


def pytest_collectreport(report):
    """A module that skips at import never becomes a test item, so it never reaches
    `pytest_runtest_logreport` at all -- it is reported once, here, as a skipped COLLECTOR.

    That is precisely how `tests/test_assay_coverage_parity.py` stayed invisible: 216 lines behind
    a module-level `pytest.skip(..., allow_module_level=True)`, counted in the summary's skip
    total and reachable by no other hook. A guard watching only run-time reports would have caught
    the four sibling-corpus arms and missed the entire module -- the largest of the five.
    """
    if report.skipped:
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        _SKIPPED.append(f"{report.nodeid}: {reason}")


def pytest_sessionfinish(session, exitstatus):
    # Only when the run was otherwise clean. A red suite has a louder problem already, and a second
    # failure stacked on top of it buries the first.
    if _SKIPPED and exitstatus == 0:
        session.config._skip_guard_failed = True
        session.exitstatus = 1


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if getattr(config, "_skip_guard_failed", False):
        terminalreporter.write_sep("=", "skipped tests are not passes", red=True)
        for entry in _SKIPPED:
            terminalreporter.write_line(f"  NOT-EVALUABLE  {entry}")
        terminalreporter.write_line(
            "  A skip reports green while measuring nothing. Assert the condition, parametrize it "
            "away, or delete the claim -- but do not let the summary count it as a pass.")
