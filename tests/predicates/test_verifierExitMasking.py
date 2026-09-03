"""tests for content.verifier_exit_masking — verifier EXIT-CODE masking.

Bar: fire on a masked VERIFIER run (TP); never fire on a legit mask of a non-verifier, an
unmasked runner, or honest stderr suppression (TN) — runner-gating + exit-code-only scoping
guarantee zero FP on the named legit cases. SCOPED 2026-06-02: the `2>/dev/null` branch was
removed (stream redirect ≠ exit masking) — graduated to blocking (error).
"""
import pytest
from makoto.checks.verifierExitMasking import predicate
from makoto.vocab import PreCheck


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


def test_silent_when_prohibition_is_a_shell_comment_after_a_verifier():
    # The verifier is executed, but the masking text is prose in a comment, not shell syntax.
    assert predicate(current_event=_bash("pytest tests/ -q  # never mask this with || true"), history=[], pattern=_PAT) is None


def test_still_fires_when_mask_is_executed_after_a_verifier():
    assert predicate(current_event=_bash("pytest tests/ -q || true"), history=[], pattern=_PAT) is not None


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
# content.verifier_exit_masking strips ~7 launcher prefixes but originally tested only 4 TP + 3 TN; cover pdm/hatch/pipenv/pnpm.

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
    "pytest", "go test ./...", "cargo test", "cargo check", "npm test", "npm run test", "npm run lint", "npm check", "yarn test", "yarn lint", "pnpm test", "pnpm check",
    "jest", "vitest", "mocha", "tsc", "ruff", "ruff check", "ruff format .", "eslint", "flake8", "mypy", "pyright", "pylint",
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


# --- THE WIDE LOCAL-VERIFIER TIER (2026-09-03): recognized, but ADVISORY, never blocking -------
# The recall hole: _LEAD_RUNNER_RX knows pytest / go test / npm test and is blind to this
# estate's own shapes. Widening a BLOCK vocabulary is expensive, so recognition is widened only
# under ADVISE. These tests pin BOTH halves of that asymmetry — a miss caught, and a deny NOT
# spent on it.

_LOCAL_MASKED = [
    "python3 -m unittest discover || true",
    "./gates.sh || true",
    "python3 tools/render_checks.py --check ; true",
    "bash ci-check.sh || echo skip",
    "python -m coverage run -m unittest || true",
]


@pytest.mark.parametrize("command", _LOCAL_MASKED)
def test_local_verifier_mask_is_recognized(command):
    f = predicate(current_event=_bash(command), history=[], pattern=_PAT)
    assert f is not None, f"recall hole still open: {command!r} masked and unseen"


@pytest.mark.parametrize("command", _LOCAL_MASKED)
def test_local_verifier_mask_never_blocks(command):
    """THE ASYMMETRY. The wide tier rests on file NAMING, a heuristic, so it may only surface.
    `level="advisory"` routes through dispatch._OUTCOME_FOR_LEVEL to verdict.ADVISE, which at
    the Pre edge allows the call and injects additionalContext."""
    f = predicate(current_event=_bash(command), history=[], pattern=_PAT)
    assert f.level == "advisory", f"a naming heuristic must never deny a call: {command!r}"


def test_narrow_block_tier_is_unchanged_by_the_widening():
    """The widening must not leak into the blocking tier: a _LEAD_RUNNER_RX runner still denies."""
    for command in ("pytest tests/ -q || true", "go test ./... ; true", "npm test || true",
                    "python -m pytest || true"):
        f = predicate(current_event=_bash(command), history=[], pattern=_PAT)
        assert f is not None and f.level == "error", f"BLOCK tier weakened by the widening: {command!r}"


def test_local_tier_does_not_fire_on_an_unmasked_local_verifier():
    assert predicate(current_event=_bash("./gates.sh"), history=[], pattern=_PAT) is None
    assert predicate(current_event=_bash("python3 -m unittest discover"), history=[], pattern=_PAT) is None


def test_local_tier_does_not_fire_on_a_masked_non_verifier_script():
    """FP-safety of the naming heuristic: an ordinary script is not a verifier."""
    for command in ("./deploy.sh || true", "python3 manage.py migrate || true",
                    "bash setup.sh || true"):
        assert predicate(current_event=_bash(command), history=[], pattern=_PAT) is None, command


def test_the_wide_tier_residue_is_stated_and_real():
    """THE MISS IS COUNTED, NOT HIDDEN. The wide tier is itself a closed list keyed on file
    naming, and this pins its documented residue rather than pretending coverage is total:
    a verifier whose name carries no verification word is NOT recognized. This test exists so
    the limit is a measured fact in the suite, not a sentence in a docstring nobody re-derives.
    If a future change closes one of these, MOVE it to _LOCAL_MASKED — do not delete the case.
    """
    for command in ("python3 eval/replay.py || true", "./go || true",
                    "./bin/verify-everything || true"):
        assert predicate(current_event=_bash(command), history=[], pattern=_PAT) is None, (
            f"{command!r} is now recognized — good; move it into _LOCAL_MASKED and shrink the "
            "residue list in the module docstring")


def test_live_catalog_registration_is_reachable_in_dispatch():
    """Every test above drives predicate() through the synthetic _PAT (a test-fixture shape),
    so nothing pinned the LIVE registration: the real CHECK's keywords could be neutered and
    the whole suite stayed green. This pins the live wiring end to end: the catalog entry for
    content.verifier_exit_masking must carry a predicate module, be admitted by dispatch's own
    keyword prefilter for a representative masked-verifier Bash payload, and fire through that
    entry."""
    import json
    from makoto import dispatch
    from makoto.registry import load_precheck_catalog

    check = next(c for c in load_precheck_catalog() if c.id == "content.verifier_exit_masking")
    assert check.predicate_module, "live check lost its predicate module: unreachable in dispatch"
    evt = _bash("pytest tests/ -q || true")
    assert dispatch._keyword_hit(check, json.dumps(evt)), (
        "live keywords no longer admit a masked verifier command: "
        "content.verifier_exit_masking is unreachable in dispatch")
    f = predicate(current_event=evt, history=[], pattern=check)
    assert f is not None and f.pattern_id == "content.verifier_exit_masking"
