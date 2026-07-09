"""tests for pattern 1.21 — verifier EXIT-CODE masking.

Bar: fire on a masked VERIFIER run (TP); never fire on a legit mask of a non-verifier, an
unmasked runner, or honest stderr suppression (TN) — runner-gating + exit-code-only scoping
guarantee zero FP on the named legit cases. SCOPED 2026-06-02: the `2>/dev/null` branch was
removed (stream redirect ≠ exit masking) — graduated to blocking (error).
"""
import pytest
from makoto.checks.verifierExitMasking import predicate
from makoto.core.schema import PreCheck


_PAT = PreCheck(
    id="content.verifier_exit_masking",
    fire_level="error",
    description="verifier exit-code masking",
    retry_hint="Don't mask a verifier's failure (|| true / ; true / set +e). Run it and fix what fails.",
)


def _bash(command: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}


# --- TP: a verifier's failure is masked ---

def test_fires_on_pytest_or_true():
    f = predicate(current_event=_bash("pytest tests/ -q || true"), history=[], pattern=_PAT)
    assert f is not None and f.pattern_id == "content.verifier_exit_masking" and f.level == "error"


def test_silent_on_runner_devnull_is_honest_stderr():
    # SCOPED 2026-06-02: `2>/dev/null` only redirects the stderr STREAM; it does NOT alter $? — a real
    # test failure still exits nonzero. Silencing stderr is honest noise-suppression, NOT exit masking.
    # The devnull branch was the predicate's only corpus-FP source (2 honest-diagnostic fires); it is gone.
    assert predicate(current_event=_bash("npm test 2>/dev/null"), history=[], pattern=_PAT) is None
    assert predicate(current_event=_bash("pytest tests/ 2>/dev/null"), history=[], pattern=_PAT) is None


def test_fires_on_go_test_semicolon_true():
    assert predicate(current_event=_bash("go test ./... ; true"), history=[], pattern=_PAT) is not None


def test_fires_on_ruff_check_or_colon():
    assert predicate(current_event=_bash("ruff check . || :"), history=[], pattern=_PAT) is not None


def test_fires_on_set_plus_e_around_pytest():
    assert predicate(current_event=_bash("set +e; pytest tests/; set -e"), history=[], pattern=_PAT) is not None


# --- TN: legit masks (non-verifier) or unmasked runners — no false positive ---

def test_silent_on_pip_uninstall_or_true():
    assert predicate(current_event=_bash("pip uninstall -y oldpkg || true"), history=[], pattern=_PAT) is None


def test_silent_on_rm_build_devnull():
    assert predicate(current_event=_bash("rm -rf build 2>/dev/null"), history=[], pattern=_PAT) is None


def test_silent_on_find_devnull():
    assert predicate(current_event=_bash("find / -name pytest 2>/dev/null"), history=[], pattern=_PAT) is None


def test_silent_on_mask_on_nonrunner_after_runner():
    # the 2>/dev/null is on `rm`, NOT on pytest (different statement) -> no fire
    assert predicate(current_event=_bash("pytest tests/ && rm tmp 2>/dev/null"), history=[], pattern=_PAT) is None


def test_silent_on_clean_pytest():
    assert predicate(current_event=_bash("pytest tests/ -q"), history=[], pattern=_PAT) is None


def test_silent_on_verb_inside_quotes():
    assert predicate(current_event=_bash('echo "run: pytest || true"'), history=[], pattern=_PAT) is None


# --- TP: launcher-delegated runners (closes the deferred python -m / poetry run / npx FNs) ---

def test_fires_on_python_m_pytest_or_true():
    assert predicate(current_event=_bash("python -m pytest tests/ || true"), history=[], pattern=_PAT) is not None


def test_fires_on_poetry_run_pytest_or_true():
    assert predicate(current_event=_bash("poetry run pytest || true"), history=[], pattern=_PAT) is not None


def test_fires_on_npx_eslint_or_true():
    assert predicate(current_event=_bash("npx eslint . || true"), history=[], pattern=_PAT) is not None


def test_fires_on_uv_run_pytest_or_true():
    assert predicate(current_event=_bash("uv run pytest || true"), history=[], pattern=_PAT) is not None


# --- TN: launcher delegating to a NON-runner must NOT fire (FP-safety of the widening) ---

def test_silent_on_python_m_pip_install():
    assert predicate(current_event=_bash("python -m pip install -e . || true"), history=[], pattern=_PAT) is None


def test_silent_on_poetry_run_python_app():
    assert predicate(current_event=_bash("poetry run python app.py 2>/dev/null"), history=[], pattern=_PAT) is None


def test_silent_on_npx_nonrunner():
    assert predicate(current_event=_bash("npx create-react-app myapp || true"), history=[], pattern=_PAT) is None


# --- coverage: the REMAINING launchers (grumpy self-audit: close the FP-safe-claim scope gap) ---
# 1.21 strips ~7 launcher prefixes but originally tested only 4 TP + 3 TN; cover pdm/hatch/pipenv/pnpm.

def test_fires_on_pdm_run_pytest():
    assert predicate(current_event=_bash("pdm run pytest || true"), history=[], pattern=_PAT) is not None


def test_fires_on_hatch_run_pytest_or_true():
    assert predicate(current_event=_bash("hatch run pytest || true"), history=[], pattern=_PAT) is not None


def test_fires_on_pipenv_run_mypy_or_true():
    assert predicate(current_event=_bash("pipenv run mypy . || true"), history=[], pattern=_PAT) is not None


def test_fires_on_pnpm_exec_jest_or_true():
    assert predicate(current_event=_bash("pnpm exec jest || true"), history=[], pattern=_PAT) is not None


def test_fires_on_pnpm_dlx_vitest_or_true():
    assert predicate(current_event=_bash("pnpm dlx vitest run || true"), history=[], pattern=_PAT) is not None


def test_silent_on_hatch_run_python():
    assert predicate(current_event=_bash("hatch run python build.py 2>/dev/null"), history=[], pattern=_PAT) is None


def test_silent_on_pdm_run_nonrunner():
    assert predicate(current_event=_bash("pdm run python manage.py migrate || true"), history=[], pattern=_PAT) is None


def test_silent_on_pnpm_exec_nonrunner():
    assert predicate(current_event=_bash("pnpm exec prettier --write . || true"), history=[], pattern=_PAT) is None


# --- SCOPE LOCK (grumpy coverage audit): EVERY runner family declared in _LEAD_RUNNER_RX must fire
# when masked. Locks test coverage to the CLAIMED scope (a minimum floor) so a future regex edit
# can't silently break an untested family. All 31 verified firing 2026-05-29.
_RUNNER_FAMILIES = [
    "pytest", "go test ./...", "cargo test", "cargo check", "npm test", "yarn test", "pnpm test",
    "jest", "vitest", "mocha", "tsc", "ruff check", "eslint", "flake8", "mypy", "pyright", "pylint",
    "make test", "make check", "make lint", "bazel test", "dotnet test", "gradle test", "gradle check",
    "mvn test", "phpunit", "rspec", "ctest", "dune test", "dune build", "swift test",
]


@pytest.mark.parametrize("runner", _RUNNER_FAMILIES)
def test_every_declared_runner_family_fires_when_masked(runner):
    assert predicate(current_event=_bash(f"{runner} || true"), history=[], pattern=_PAT) is not None


# --- LINE-LEVEL PINS (mutation-audit gaps): the leading VAR= strip, the _WRAPPERS strip,
# and the inner VAR= skip are reached ONLY by these wrapper/prefix shapes — a region no prior
# test exercised. Each input fires on the original but goes silent under the named mutation. ---

def test_fires_on_env_var_pytest_or_true():
    # PIN L50 (CMP `i < len(toks)` in the leading VAR= strip loop): the mutant `i > len(toks)`
    # never strips `HOME=/tmp`, so the leading command reads as `HOME=/tmp pytest` (regex `^`
    # anchor fails) -> mutant silent. Original strips VAR= and sees `pytest` -> fires.
    assert predicate(current_event=_bash("HOME=/tmp pytest tests/ || true"), history=[], pattern=_PAT) is not None


def test_fires_on_sudo_pytest_or_true():
    # PIN L52 (CMP `i < len(toks)` in the _WRAPPERS strip loop): the mutant `i > len(toks)`
    # never enters the wrapper loop, so `sudo` reads as the leading command (not a runner) ->
    # mutant silent. Original strips the `sudo` wrapper and sees `pytest` -> fires.
    assert predicate(current_event=_bash("sudo pytest tests/ || true"), history=[], pattern=_PAT) is not None


def test_fires_on_env_var_eq_pytest_or_true():
    # PIN L54 (BOTH the BOOL `and`->`or` AND the CMP `i < len(toks)` in the inner VAR= skip):
    #  - BOOL `or`: the inner skip becomes true for any non-dash token, over-skipping past
    #    `pytest` to the end of the token list (empty tail) -> mutant silent / raises.
    #  - CMP `i > len(toks)`: the inner loop never runs, so `VAR=1` is not skipped and the
    #    wrapper loop lands on `VAR=1 pytest` (regex fails) -> mutant silent.
    # Original strips `env` then `VAR=1`, sees `pytest` -> fires.
    assert predicate(current_event=_bash("env VAR=1 pytest tests/ || true"), history=[], pattern=_PAT) is not None


def test_fires_when_unmasked_runner_precedes_masked_runner():
    # PIN L92 (NOT `if reason:`->`if not reason:` early-exit): with an UNMASKED runner FIRST and a
    # MASKED runner SECOND, the mutant `if not reason: break` exits at the first (unmasked) runner
    # before reason is ever set -> mutant silent. Original keeps scanning, reaches the masked second
    # runner, sets reason, and fires. (The triage's `pytest||true && npm test` fires on BOTH versions
    # and does NOT redden — this ordering is the verified distinguishing input.)
    assert predicate(current_event=_bash("pytest tests/ && pytest other/ || true"), history=[], pattern=_PAT) is not None
