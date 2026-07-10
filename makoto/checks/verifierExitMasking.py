"""content.verifier_exit_masking — verifier EXIT-CODE masking (a test/build/lint runner's failure hidden).

Forcing a verifier's exit code to 0 — `pytest || true`, `go test ; true`, `set +e` around a
runner — manufactures a green that survives real failures. A core honesty cheat (CLAUDE.md
commandment 1: no `|| true` / `; true` / `set +e` to hide failures).

SCOPED to exit-code masking ONLY (2026-06-02 graduation). The `2>/dev/null` / `&>/dev/null` branch
was REMOVED: stream redirection does NOT alter `$?` (`sys.exit(7) 2>/dev/null` still exits 7) — every
runner in _LEAD_RUNNER_RX signals failure via a nonzero exit, so silencing stderr cannot turn a real
failure into a green. The devnull branch detected honest stderr-noise suppression, not failure-masking
(a category error), and was the predicate's only false-positive source on the real corpus (2 fires,
both honest diagnostics). Removing it drives corpus-FP to 0 → graduated to BLOCKING.

FP-SAFE BY RUNNER-GATING, and the runner must be the LEADING command of a statement (an actual
invocation), NOT an argument — so `find / -name pytest || true` does NOT fire (find is the command).
Legit masks on NON-runners (pip uninstall||true, rm -rf build || true) carry no leading runner ->
never fire. The mask must be in the SAME statement as the runner. `python -m` / `poetry run` / `npx`
/ `pnpm exec|dlx` / `uv|pdm|hatch|pipenv run` launcher prefixes ARE handled (stripped to the delegated
runner, FP-safe). The bare `<tool> test/check` fallback (unknown tool, no launcher) remains DEFERRED.

Knight-Leveson: stdlib re only.
"""
# jscpd note (2026-07-09): flagged as a clone against illusoryAuthorshipTrailer.py. Verified: the
# matched span is only this docstring's closing "Knight-Leveson" line + the standard
# `from __future__ import annotations` / `import re` / `from typing import Optional` /
# `from makoto.core.schema import Finding, PreCheck` header both Pre-hook predicate modules need --
# it ends before any function body, so no logic is shared (this module's runner/exit-mask
# detection is unrelated to illusoryAuthorshipTrailer's Claude-authorship-trailer regex). See
# tests/test_no_alpha_duplicate_functions.py for the package's real duplicate-logic gate.
from __future__ import annotations
import re
from typing import Optional
from makoto.core.schema import Finding, PreCheck
from makoto.core.lexicons import _QUOTED_RX  # L0 shared lexicon (dedup: was a byte-identical local copy)

# Anchored at the (post-wrapper) START of a statement: the runner is INVOKED, not an argument.
_LEAD_RUNNER_RX = re.compile(
    r"^(?:pytest|go\s+test|cargo\s+(?:test|check)|(?:npm|yarn|pnpm)\s+(?:run\s+)?(?:test|check|lint)"
    r"|jest|vitest|mocha|tsc|ruff|eslint|flake8|mypy|pyright|pylint|make\s+(?:test|check|lint)"
    r"|bazel\s+test|dotnet\s+test|gradle\s+(?:test|check)|mvn\s+test|phpunit|rspec|ctest"
    r"|dune\s+(?:test|build)|swift\s+test)\b"
)
_WRAPPERS = ("sudo", "env", "time", "nice", "exec", "command", "builtin")
_MASK_TAIL_RX = re.compile(r"(?:\|\|\s*(?:true|:))(?:\s|$)")  # ; true handled separately (it splits)
_SETE_RX = re.compile(r"\bset\s+\+e\b")


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


def predicate(*, current_event: dict, history: list, pattern: PreCheck,
              conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    if current_event.get("tool_name") != "Bash":
        return None
    raw = current_event.get("tool_input", {}).get("command", "")
    cmd = _QUOTED_RX.sub(" ", raw)
    parts = re.split(r"(&&|;|\n)", cmd)  # commands at even indices, separators at odd
    set_e = bool(_SETE_RX.search(cmd))

    reason = None
    for idx in range(0, len(parts), 2):
        c = parts[idx]
        if not _is_runner_command(c):
            continue
        if _MASK_TAIL_RX.search(c):  # `|| true` / `|| :` within the runner statement
            reason = "verifier failure masked by `|| true`"
        elif idx + 2 < len(parts) and parts[idx + 1].strip() == ";" and parts[idx + 2].strip() in ("true", ":"):
            reason = "verifier failure masked by `; true`"  # `; true` makes exit 0 regardless
        elif set_e:
            reason = "`set +e` disables exit-on-error around a verifier"
        if reason:
            break

    if reason:
        return Finding(
            pattern_id=pattern.id, file="", line=0, level=pattern.fire_level,
            message=f"row {pattern.id} ({pattern.description}): {reason} — a hidden failure reads as success",
            retry_hint=pattern.retry_hint, snippet=raw[:120],
        )
    return None


from makoto.substrate._loader import Check as _Check
RETRY_HINT = "Don't mask a verifier's failure with || true / ; true / set +e. Run the test/build/lint and fix what fails -- a hidden failure that reads as success is a cheat."
DESCRIPTION = 'verifier exit-code masking (|| true / ; true / set +e on a test/build/lint runner)'

CHECK = _Check(id='content.verifier_exit_masking', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('|| true', '; true', '|| :', 'set +e'), retry_hint=RETRY_HINT, description=DESCRIPTION)
