"""content.verifier_exit_masking — verifier EXIT-CODE masking (a test/build/lint runner's failure hidden).

Forcing a verifier's exit code to 0 — `pytest || true`, `go test ; true`, `set +e` around a
runner — manufactures a green that survives real failures. A core honesty cheat (CLAUDE.md
commandment 1: no `|| true` / `; true` / `set +e` to hide failures).

SCOPED to exit-code masking ONLY. Stream redirection (`2>/dev/null` / `&>/dev/null`) is deliberately
OUT of scope: it does NOT alter `$?` (`sys.exit(7) 2>/dev/null` still exits 7) — every runner in
_LEAD_RUNNER_RX signals failure via a nonzero exit, so silencing stderr cannot turn a real failure
into a green. See docs/adr/0049-verifier-exit-masking-devnull-branch-removal.md for the decision
history.

FP-SAFE BY SHELL COMMAND POSITION: this check tokenizes the Bash command and only treats a runner,
mask, or `set +e` as evidence when it is an executed command/operator, not prose in a comment,
quoted string, or Markdown/code-fence payload. This is necessarily heuristic rather than a Bash
interpreter: malformed shell, heredocs, `eval`, and dynamically-built commands can still be
misclassified or missed.

The runner must be the LEADING command of a statement (an actual invocation), NOT an argument — so
`find / -name pytest || true` does NOT fire (find is the command).
Legit masks on NON-runners (pip uninstall||true, rm -rf build || true) carry no leading runner ->
never fire. The mask must be in the SAME statement as the runner. `python -m` / `poetry run` / `npx`
/ `pnpm exec|dlx` / `uv|pdm|hatch|pipenv run` launcher prefixes ARE handled (stripped to the delegated
runner, FP-safe). The bare `<tool> test/check` fallback (unknown tool, no launcher) remains DEFERRED.

Knight-Leveson: stdlib re only.
"""
# See docs/adr/0035-jscpd-clone-flag-verifications.md for why this module's jscpd clone flag
# against illusoryAuthorshipTrailer.py was verified and dismissed (only shared span is the
# standard predicate-module docstring/import header, no logic in common).
# tests/test_no_alpha_duplicate_functions.py is the package's real duplicate-logic gate.
from __future__ import annotations
import re
from typing import Optional
from makoto.vocab import Finding
from makoto.registry import Check
from makoto.core._shell import _shell_segments

# Anchored at the (post-wrapper) START of a statement: the runner is INVOKED, not an argument.
_LEAD_RUNNER_RX = re.compile(
    r"^(?:pytest|go\s+test|cargo\s+(?:test|check)|(?:npm|yarn|pnpm)\s+(?:run\s+)?(?:test|check|lint)"
    r"|jest|vitest|mocha|tsc|ruff|eslint|flake8|mypy|pyright|pylint|make\s+(?:test|check|lint)"
    r"|bazel\s+test|dotnet\s+test|gradle\s+(?:test|check)|mvn\s+test|phpunit|rspec|ctest"
    r"|dune\s+(?:test|build)|swift\s+test)\b"
)
_WRAPPERS = ("sudo", "env", "time", "nice", "exec", "command", "builtin")
def _is_runner_command(c: str) -> bool:
    """True iff the statement's LEADING command (after VAR= / wrappers / launcher prefixes) is a verifier.

    Launcher prefixes that DELEGATE to a runner are stripped so the runner becomes leading:
    `python -m pytest`, `poetry run pytest`, `npx eslint`, `pnpm exec jest`, `uv|pdm|hatch|pipenv run <runner>`.
    FP-SAFE: `python -m pip install` / `poetry run python app.py` keep a NON-runner leading -> never fire.
    """
    toks = c.strip().split()
    i = 0
    while i < len(toks) and "=" in toks[i] and not toks[i].startswith("-"):
        i += 1
    while i < len(toks) and toks[i] in _WRAPPERS:
        i += 1
        while i < len(toks) and "=" in toks[i] and not toks[i].startswith("-"):
            i += 1
    # Strip ONE launcher prefix that delegates to a real runner (the runner then leads).
    if i < len(toks):
        t = toks[i]
        if re.match(r"^python[0-9.]*$", t) and i + 1 < len(toks) and toks[i + 1] == "-m":
            i += 2
        elif t == "npx":
            i += 1
        elif t in ("poetry", "uv", "pdm", "hatch", "pipenv") and i + 1 < len(toks) and toks[i + 1] == "run":
            i += 2
        elif t == "pnpm" and i + 1 < len(toks) and toks[i + 1] in ("exec", "dlx"):
            i += 2
    return bool(_LEAD_RUNNER_RX.match(" ".join(toks[i:])))


def predicate(*, current_event: dict, history: list, pattern: Check,
              conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    if current_event.get("tool_name") != "Bash":
        return None
    raw = current_event.get("tool_input", {}).get("command", "")
    segments = _shell_segments(raw)
    set_e = any(argv[:2] == ["set", "+e"] for argv, _operator in segments)

    reason = None
    for idx, (argv, operator) in enumerate(segments):
        if not _is_runner_command(" ".join(argv)):
            continue
        next_argv = segments[idx + 1][0] if idx + 1 < len(segments) else []
        if operator == "||" and next_argv in (["true"], [":"]):
            reason = "verifier failure masked by `|| true`"
        elif operator == ";" and next_argv in (["true"], [":"]):
            reason = "verifier failure masked by `; true`"  # `; true` makes exit 0 regardless
        elif set_e:
            reason = "`set +e` disables exit-on-error around a verifier"
        if reason:
            break

    if reason:
        return Finding(
            pattern_id=pattern.id, file="", line=0, level="error",  # Pre-tier invariantly BLOCK
            message=f"row {pattern.id} ({pattern.description}): {reason} — a hidden failure reads as success",
            retry_hint=pattern.retry_hint, snippet=raw[:120],
        )
    return None


from makoto.registry import Check as _Check
RETRY_HINT = "Don't mask a verifier's failure with || true / ; true / set +e. Run the test/build/lint and fix what fails -- a hidden failure that reads as success is a cheat."
DESCRIPTION = 'verifier exit-code masking (|| true / ; true / set +e on a test/build/lint runner)'

CHECK = _Check(id='content.verifier_exit_masking', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('|| true', '; true', '|| :', 'set +e'), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "pattern"}), tests="PATTERN_MATCH")
