"""The skip guard must be seen failing, in a real session, on a planted skip of each phase.

`_skipGuard` is the reason this suite can no longer report green on tests it never ran. A guard
nobody has watched fire is exactly the shape it exists to refuse, so it is exercised here the only
way that settles it: a real `pytest` session, in a subprocess, over planted tests -- not by calling
the hooks with hand-built report objects, which would prove that the functions run and nothing
about whether pytest routes real skips through them.

That distinction is not theoretical. The guard's first version watched only the SETUP phase, which
looks right and passes any hand-built-report test you would write for it, and stayed silent on a
`pytest.skip()` in a test body -- four of the five skips it was written to catch.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# A star-import, deliberately, and only because this conftest is GENERATED. Naming the hooks here
# would be a second list of them that goes stale the day a fifth is added -- which is not
# hypothetical: the first version of this file named three while `_skipGuard` defined four, so the
# module-level case silently tested nothing. The real `tests/conftest.py` names them explicitly, as
# a checked-in file should, and `test_every_guard_hook_is_registered` below compares that list
# against the module so the two spellings cannot drift apart unnoticed.
CONFTEST = """\
import sys
sys.path.insert(0, {root!r})
from tests._skipGuard import *  # noqa: F401,F403  -- every hook the module defines
"""


def _session(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    """Run a real pytest session over `body`, with the live guard installed.

    A PASSING test is always planted alongside, and it is load-bearing rather than decoration. A
    directory whose only file skips at module level collects nothing, and pytest exits 5 ("no tests
    collected") on its own -- so an assertion that the session went red would pass without the
    guard having done anything, which is how the module-level case first looked green here. With a
    real test present the session's own status is 0, and any red is the guard's doing.
    """
    (tmp_path / "conftest.py").write_text(CONFTEST.format(root=str(REPO_ROOT)), encoding="utf-8")
    (tmp_path / "test_planted.py").write_text(textwrap.dedent(body), encoding="utf-8")
    (tmp_path / "test_companion.py").write_text("def test_real():\n    assert True\n",
                                                encoding="utf-8")
    return subprocess.run([sys.executable, "-m", "pytest", "-q", str(tmp_path)],
                          cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)


def test_TEETH_a_body_skip_turns_the_session_red(tmp_path):
    """The phase the first version of this guard missed."""
    done = _session(tmp_path, """
        import pytest
        def test_planted_body_skip():
            pytest.skip("planted: a sibling that will never exist")
    """)
    assert done.returncode != 0, f"a skipped test reported green:\n{done.stdout}{done.stderr}"
    assert "NOT-EVALUABLE" in done.stdout
    assert "test_planted_body_skip" in done.stdout


def test_TEETH_a_setup_skip_turns_the_session_red(tmp_path):
    done = _session(tmp_path, """
        import pytest
        @pytest.mark.skipif(True, reason="planted: setup-phase skip")
        def test_planted_setup_skip():
            assert False
    """)
    assert done.returncode != 0, f"a skipped test reported green:\n{done.stdout}{done.stderr}"
    assert "NOT-EVALUABLE" in done.stdout
    assert "test_planted_setup_skip" in done.stdout


def test_TEETH_a_module_level_skip_turns_the_session_red(tmp_path):
    """How the assay coverage-parity module hid: the skip is raised at import."""
    done = _session(tmp_path, """
        import pytest
        pytest.skip("planted: monorepo docs not present", allow_module_level=True)
        def test_never_collected():
            assert False
    """)
    assert done.returncode != 0, f"a skipped module reported green:\n{done.stdout}{done.stderr}"
    assert "NOT-EVALUABLE" in done.stdout


def test_a_clean_session_stays_green(tmp_path):
    """Without this, a guard that failed every session would pass all three checks above."""
    done = _session(tmp_path, """
        def test_real():
            assert 1 + 1 == 2
    """)
    assert done.returncode == 0, f"a clean session was failed by the guard:\n{done.stdout}"
    assert "NOT-EVALUABLE" not in done.stdout


def test_every_guard_hook_is_registered():
    """`tests/conftest.py` names the hooks it imports, and pytest only calls what is named.

    A hook added to `_skipGuard` and not added there is dead: registered nowhere, called never,
    and silent in exactly the way the guard exists to refuse. That is not a hypothetical either --
    `pytest_collectreport` was written, imported by nothing, and the module-level-skip case above
    reported green because of it.
    """
    from tests import _skipGuard, conftest
    defined = {n for n in vars(_skipGuard) if n.startswith("pytest_")}
    missing = sorted(h for h in defined if not hasattr(conftest, h))
    assert not missing, (f"hooks defined in _skipGuard but not imported into tests/conftest.py, "
                         f"so pytest never calls them: {missing}")


def test_an_xfail_is_not_counted_as_a_skip(tmp_path):
    """pytest reports an xfailed test as skipped. An xfail RAN and is a recorded expectation, so
    counting it here would make the guard fire on a suite that is doing exactly the right thing --
    and this repository has one."""
    done = _session(tmp_path, """
        import pytest
        @pytest.mark.xfail(reason="a recorded, named expectation")
        def test_expected_to_fail():
            assert False
    """)
    assert done.returncode == 0, f"an xfail was counted as a skip:\n{done.stdout}"
    assert "NOT-EVALUABLE" not in done.stdout
