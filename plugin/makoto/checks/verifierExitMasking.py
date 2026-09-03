"""content.verifier_exit_masking — verifier EXIT-CODE masking (a test/build/lint runner's failure hidden).

Forcing a verifier's exit code to 0 — `pytest || true`, `go test ; true`, an unrestored
`set +e` before a runner, a masking `||` branch (`pytest || echo skip`), a trailing pipe
(`pytest | tail -5` without pipefail), an `if` wrapper with no failing branch, a `$?`
captured but never returned, or a subshell/brace group around any of these — manufactures
a green that survives real failures. A core honesty cheat (CLAUDE.md commandment 1: no
`|| true` / `; true` / `set +e` to hide failures). An `||`/`if` branch that RE-RAISES the
failure (`pytest || exit 1`, `if pytest; ... else exit 1; fi`, `... exit $rc`) is honest
handling and never fires.

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

TWO RUNNER TIERS WITH DIFFERENT POSTURES (2026-09-03). `_LEAD_RUNNER_RX` is a foreign-ecosystem
vocabulary — pytest, go test, npm test — and was blind to this estate's OWN verifier shapes
(`python3 -m unittest`, `python3 tools/render_checks.py`, `./gates.sh`), so masks on them passed
unseen. Recognition is widened by `_is_local_runner_command`, but ONLY under ADVISE:

  * BLOCK (`level="error"`, a PreToolUse deny) remains bound to `_LEAD_RUNNER_RX` alone. Widening
    a blocking vocabulary is expensive — every added token can deny a call on a guess — so the
    blocking tier is UNCHANGED.
  * ADVISE (`level="advisory"`, allow + additionalContext) carries the wider tier. It rests on
    FILE NAMING, which is a heuristic, and a heuristic must not deny.

WHAT THE WIDE TIER STILL CANNOT DECIDE, stated so the miss is counted rather than invisible: a
verifier whose name carries no verification word — `python3 eval/replay.py`, `./go`,
`./bin/verify-everything` — is RESIDUE. It is neither blocked nor surfaced, and this check does
not know it was a verifier. The wide tier is itself a closed list; the difference is that its
residue costs a missing advisory, never a false block.

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
from makoto.core._shell import (_NESTED_SHELL_PROGRAMS, _basename, _effective_argv,
                                _shell_segments)

# Anchored at the (post-wrapper) START of a statement: the runner is INVOKED, not an argument.
_LEAD_RUNNER_RX = re.compile(
    r"^(?:pytest|go\s+test|cargo\s+(?:test|check)|(?:npm|yarn|pnpm)\s+(?:run\s+)?(?:test|check|lint)"
    r"|jest|vitest|mocha|tsc|ruff|eslint|flake8|mypy|pyright|pylint|make\s+(?:test|check|lint)"
    r"|bazel\s+test|dotnet\s+test|gradle\s+(?:test|check)|mvn\s+test|phpunit|rspec|ctest"
    r"|dune\s+(?:test|build)|swift\s+test)\b"
)

# --- the SECOND, WIDER runner tier: this estate's own verifier shapes (ADVISE only) -----------
# _LEAD_RUNNER_RX above is a foreign-ecosystem vocabulary — pytest, go test, npm test, cargo,
# gradle. It is blind to how THIS repository actually verifies itself: `python3 -m pytest` is
# covered only by accident of the `-m` strip, while `python3 tools/render_checks.py --check`,
# `python3 eval/replay.py`, `python3 -m unittest`, and `./gates.sh` are not recognized at all.
# A mask on any of those is a real hidden failure that this check silently allowed.
#
# THE ASYMMETRY, stated because it is the whole design and it costs something:
#   * BLOCK (level="error") stays bound to _LEAD_RUNNER_RX alone. It is UNCHANGED by this
#     widening. A deny is expensive and irreversible-ish for the agent's turn, so it is only
#     ever spent on a token whose runner-hood is unambiguous.
#   * ADVISE (level="advisory") carries the wider tier. A `.py` script is not necessarily a
#     verifier and a `.sh` script named `check-something` may be a deploy step; the wider tier
#     is a HEURISTIC over file naming, and a heuristic must not deny. It allows the call and
#     injects context naming the mask.
# The price paid deliberately: a genuinely masked `./gates.sh || true` is now SURFACED but NOT
# STOPPED. Recognition without a block is worth more than no recognition; a block on this
# evidence would be worth less than nothing.
#
# THIS TIER IS ALSO A CLOSED LIST, and says so. Its residue — an unlisted local verifier — costs
# an ADVISORY that never appears, never a false block. That is why widening here is affordable
# and widening _LEAD_RUNNER_RX would not be.
_LOCAL_SCRIPT_VERIFIER_RX = re.compile(
    r"(?:^|[/\\_.-])(?:gate|gates|test|tests|check|checks|lint|verify|ci|preflight|smoke)"
    r"(?:[._-][A-Za-z0-9_.-]*)?\.(?:sh|bash|py)$"
)
_LOCAL_MODULE_RUNNERS = frozenset({"unittest", "pytest", "nose2", "green", "tox", "nox", "coverage"})

_WRAPPERS = frozenset({"sudo", "env", "time", "nice", "exec", "command", "builtin"})
_PYTHON_RX = re.compile(r"python[0-9.]*")
# Launcher -> the subcommands after which the next token is the delegated runner.
_LAUNCHER_SUBCOMMANDS = {
    "poetry": ("run",), "uv": ("run",), "pdm": ("run",), "hatch": ("run",),
    "pipenv": ("run",), "pnpm": ("exec", "dlx"),
}


def _skip_assignments(toks: list, i: int) -> int:
    """Advance past leading ``VAR=value`` tokens."""
    while i < len(toks) and "=" in toks[i] and not toks[i].startswith("-"):
        i += 1
    return i


def _leading_tokens(c: str) -> list:
    """The statement's tokens from its LEADING command onward, after stripping leading `VAR=`
    assignments, `_WRAPPERS`, and ONE launcher prefix that delegates to a real runner
    (`python -m X`, `npx X`, `poetry|uv|pdm|hatch|pipenv run X`, `pnpm exec|dlx X`).

    Extracted so BOTH runner tiers normalize identically: the narrow blocking tier
    (`_is_runner_command`) and the wide advisory tier (`_is_local_runner_command`) must agree on
    which token is "leading", or `sudo ./gates.sh || true` would be read one way by one tier and
    another way by the other."""
    toks = c.strip().split()
    i = _skip_assignments(toks, 0)
    while i < len(toks) and toks[i] in _WRAPPERS:
        i = _skip_assignments(toks, i + 1)
    if i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if _PYTHON_RX.fullmatch(t) and nxt == "-m":
            i += 2
        elif t == "npx":
            i += 1
        elif nxt is not None and nxt in _LAUNCHER_SUBCOMMANDS.get(t, ()):
            i += 2
    return toks[i:]


def _is_runner_command(c: str) -> bool:
    """True iff the statement's LEADING command (after VAR= / wrappers / launcher prefixes) is a verifier.

    THE BLOCKING TIER, deliberately NARROW and UNCHANGED by the 2026-09-03 widening: only
    `_LEAD_RUNNER_RX`'s explicit foreign-ecosystem runner names. A deny is only ever spent here.

    Launcher prefixes that DELEGATE to a runner are stripped so the runner becomes leading:
    `python -m pytest`, `poetry run pytest`, `npx eslint`, `pnpm exec jest`, `uv|pdm|hatch|pipenv run <runner>`.
    FP-SAFE: `python -m pip install` / `poetry run python app.py` keep a NON-runner leading -> never fire.
    """
    return bool(_LEAD_RUNNER_RX.match(" ".join(_leading_tokens(c))))


def _is_local_runner_command(c: str) -> bool:
    """True iff the leading command is one of THIS ESTATE's verifier shapes that
    `_LEAD_RUNNER_RX` cannot see. THE ADVISORY TIER — never a block. See the asymmetry note at
    `_LOCAL_SCRIPT_VERIFIER_RX`.

    Recognized: `python -m unittest|nose2|tox|nox|coverage|...` (the module runners), and a
    directly-executed script whose FILE NAME carries a verification word
    (`./gates.sh`, `python3 tools/render_checks.py`, `bash ci-check.sh`, `./run_tests.py`).

    WHAT THIS CANNOT DECIDE, named so the miss is counted rather than invisible:
      * A verifier whose file name says nothing — `python3 eval/replay.py`, `./go`, `make all`,
        `./bin/verify-everything` (no extension). Recognition rests on NAMING, and a script is
        under no obligation to be named honestly. These are RESIDUE: no advisory is emitted, and
        nothing is blocked. The gate does not know they were verifiers.
      * Whether a matched name IS a verifier. `check-deploy.sh` matches and may well be a deploy
        step. This is exactly why the tier is advisory: the false-positive cost is one line of
        injected context, not a denied call.
    Neither direction of this ambiguity may reach `level="error"`.
    """
    toks = _leading_tokens(c)
    if not toks:
        return False
    head = _basename(toks[0])
    if head in _LOCAL_MODULE_RUNNERS:
        return True                          # `python -m unittest` (the -m prefix already stripped)
    if _LOCAL_SCRIPT_VERIFIER_RX.search(toks[0]):
        return True                          # `./gates.sh`, `bash tests/ci-check.sh`
    # An interpreter invoked on a named script: `python3 tools/render_checks.py`, `bash ./gates.sh`.
    if _PYTHON_RX.fullmatch(head) or head in ("bash", "sh", "zsh"):
        for arg in toks[1:]:
            if arg.startswith("-"):
                continue
            return bool(_LOCAL_SCRIPT_VERIFIER_RX.search(arg))
    return False


_GROUP_TOKENS = frozenset({"{", "}", "};", "(", ")"})
_CONTROL_TOKENS = frozenset({"then", "else", "elif", "do", "done", "fi", "!"})
_SET_PLUS_FLAGS_RX = re.compile(r"\+[A-Za-z]+\Z")
_SET_MINUS_FLAGS_RX = re.compile(r"-[A-Za-z]+\Z")
_STATUS_CAPTURE_RX = re.compile(r"\$\?")


def _top_level_count(segments) -> int:
    """How many leading entries of `_shell_segments`' return are TOP-LEVEL statements.

    `_shell_segments` appends segments re-parsed out of quoted `bash -c`/`sh -c`/`ssh`
    payloads AFTER all top-level segments, so pairing a runner with `segments[idx + 1]`
    across that boundary attributes another shell's `; true` to a top-level runner — a DENY
    resting on a false fact. This re-derives the boundary with the segmenter's own rule."""
    top = len(segments)
    i = 0
    while i < top:
        effective = _effective_argv(segments[i][0])
        if effective and _basename(effective[0]) in _NESTED_SHELL_PROGRAMS:
            for arg in effective[1:]:
                if any(ch.isspace() for ch in arg):
                    top -= len(_shell_segments(arg))
        i += 1
    return top


def _normalized_segments(command: str):
    """`[(argv, operator, is_top)]` with subshell/brace-group punctuation dissolved.

    `(` is not a shlex punctuation char, so `(pytest` / `true)` arrive glued, and `{` / `}`
    arrive as standalone word tokens; either defeats both runner recognition and mask-literal
    matching. Group delimiters never change which command's exit survives, so they are
    stripped, and a delimiter-only segment donates its operator to the group it closed
    (`{ pytest; } || true` -> `pytest || true`). A `\\n` separator sequences exactly as `;`
    does and is normalized to it."""
    raw = _shell_segments(command)
    top = _top_level_count(raw)
    out = []
    for i, (argv, operator) in enumerate(raw):
        operator = ";" if operator == "\n" else operator
        toks = [t for t in argv if t not in _GROUP_TOKENS]
        if toks:
            toks[0] = toks[0].lstrip("(")
            toks[-1] = toks[-1].rstrip(")")
            toks = [t for t in toks if t]
        if not toks:
            if out and operator and out[-1][1] in ("", ";"):
                out[-1] = (out[-1][0], operator, out[-1][2])
            continue
        out.append((toks, operator, i < top))
    return out


def _errexit_toggle(argv):
    """For a `set` argv: True = errexit turned OFF (`+e`, `+eu`, `+ex`, `+o errexit`),
    False = turned back ON (`-e`, `-eo ...`, `-o errexit`), None = not an errexit toggle.
    Combined flag groups count: `set +eu` disables errexit exactly as `set +e` does."""
    if argv[:1] != ["set"]:
        return None
    state = None
    args = argv[1:]
    for j, a in enumerate(args):
        nxt = args[j + 1] if j + 1 < len(args) else ""
        if a == "+o" and nxt == "errexit":
            state = True
        elif a == "-o" and nxt == "errexit":
            state = False
        elif _SET_PLUS_FLAGS_RX.fullmatch(a) and "e" in a:
            state = True
        elif _SET_MINUS_FLAGS_RX.fullmatch(a) and "e" in a:
            state = False
    return state


def _pipefail_toggle(argv):
    """True/False when argv is a `set` command toggling pipefail, else None."""
    if argv[:1] != ["set"] or "pipefail" not in argv[1:]:
        return None
    return "+o" not in argv[1:]


def _is_exit_zero_literal(argv) -> bool:
    """A command that unconditionally exits 0: `true` (any path spelling) or `:`."""
    return bool(argv) and (argv[0] == ":" or _basename(argv[0]) == "true")


def _propagates_failure(argvs) -> bool:
    """True when any later same-scope segment re-raises the failure an operator swallowed:
    `exit`/`return` with a non-`0` argument (`exit 1`, `exit $rc`), bare `exit`/`return`
    (which propagate `$?`), or `false`. This separates `pytest || exit 1` and
    `if pytest; ... else exit 1; fi` (honest) from `pytest || echo skip` (masked)."""
    for argv in argvs:
        toks = [t for t in argv if t not in _CONTROL_TOKENS]
        if not toks:
            continue
        head = _basename(toks[0])
        if head == "false":
            return True
        if head in ("exit", "return"):
            arg = toks[1] if len(toks) > 1 else ""
            if arg != "0":
                return True
    return False


def predicate(*, current_event: dict, history: list, pattern: Check,
              conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    if current_event.get("tool_name") != "Bash":
        return None
    raw = current_event.get("tool_input", {}).get("command", "")
    segments = _normalized_segments(raw)

    reason = None
    # Which TIER supplied the runner for the fired `reason`. "block" = _LEAD_RUNNER_RX (the
    # narrow, unambiguous vocabulary); "advise" = _is_local_runner_command (the wide, naming-
    # heuristic estate tier). This variable is the whole asymmetry: it decides the Finding's
    # level and nothing else, and it can only ever SOFTEN — a lead-runner match always wins.
    tier = None
    # Errexit/pipefail state is tracked POSITIONALLY and PER SCOPE (top-level statements vs
    # segments re-parsed out of nested shell payloads): `set +e` masks only a runner that
    # executes AFTER it, in the SAME shell, with no restoring `set -e` in between. Anything
    # broader was measured producing DENYs on false facts (mask after the runner, mask
    # restored before it, mask inside a different shell's quoted payload).
    errexit_off = {True: False, False: False}
    pipefail_on = {True: False, False: False}
    for idx, (argv, operator, is_top) in enumerate(segments):
        errexit = _errexit_toggle(argv)
        pipefail = _pipefail_toggle(argv)
        if errexit is not None or pipefail is not None:
            if errexit is not None:
                errexit_off[is_top] = errexit
            if pipefail is not None:
                pipefail_on[is_top] = pipefail
            continue
        if_wrapped = argv[0] in ("if", "elif")
        lead = argv[1:] if if_wrapped else argv
        lead_text = " ".join(lead)
        if _is_runner_command(lead_text):
            here = "block"
        elif _is_local_runner_command(lead_text):
            here = "advise"
        else:
            continue
        # The runner's scope ends where the top-level/nested flag flips (top-level segments
        # all precede nested ones); a mask is only evidence INSIDE that scope.
        end = idx + 1
        while end < len(segments) and segments[end][2] == is_top:
            end += 1
        next_argv = segments[idx + 1][0] if idx + 1 < end else []
        rest = [a for a, _op, _t in segments[idx + 1:end]]

        if operator in ("||", ";") and _is_exit_zero_literal(next_argv):
            # Either shape forces the statement's exit to 0 regardless of the runner's.
            reason = f"verifier failure masked by `{operator} {next_argv[0]}`"
        elif operator in ("|", "|&") and not pipefail_on[is_top]:
            reason = "verifier exit code replaced by the pipeline tail's (`| ...` without pipefail)"
        elif operator == "||" and not _propagates_failure(rest):
            reason = f"verifier failure masked by `|| {' '.join(next_argv)[:40]}`"
        elif operator == "&&":
            j = idx + 1
            while j < end and segments[j][1] == "&&":
                j += 1
            if j < end and segments[j][1] == "||" \
                    and not _propagates_failure([a for a, _op, _t in segments[j + 1:end]]):
                reason = "verifier failure absorbed by the trailing `|| ...` branch"
        elif operator == ";" and next_argv \
                and any(_STATUS_CAPTURE_RX.search(t) for t in next_argv) \
                and not _propagates_failure(rest):
            reason = "verifier exit captured (`$?`) but never returned"
        if reason is None and if_wrapped and not _propagates_failure(rest):
            reason = "verifier exit consumed by `if` with no failing branch"
        if reason is None and errexit_off[is_top]:
            reason = "`set +e` disables exit-on-error around a verifier"
        if reason:
            tier = here
            break

    if reason:
        # The asymmetry lands here and NOWHERE else. `level="error"` is the Pre-tier BLOCK wire
        # (dispatch._OUTCOME_FOR_LEVEL -> verdict.BLOCK -> permissionDecision "deny").
        # `level="advisory"` is verdict.ADVISE, which at the Pre edge ALLOWS the call and injects
        # the message as additionalContext. A widened-recognition hit is surfaced, never denied.
        advisory = tier == "advise"
        note = (" — recognized by the WIDE local-verifier tier (a naming heuristic), so this is "
                "SURFACED, not blocked") if advisory else ""
        return Finding(
            pattern_id=pattern.id, file="", line=0,
            level="advisory" if advisory else "error",
            message=(f"row {pattern.id} ({pattern.description}): {reason} — a hidden failure "
                     f"reads as success{note}"),
            retry_hint=pattern.retry_hint, snippet=raw[:120],
        )
    return None


from makoto.registry import Check as _Check
RETRY_HINT = "Don't mask a verifier's failure with || true / ; true / a masking || branch / a trailing pipe / an if wrapper / set +e. Run the test/build/lint and fix what fails -- a hidden failure that reads as success is a cheat."
DESCRIPTION = 'verifier exit-code masking (|| true / ; true / masking || branch / trailing pipe / if wrapper / $? dropped / set +e on a test/build/lint runner)'

CHECK = _Check(id='content.verifier_exit_masking', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('|', ';', 'set +', '$?', 'if ', 'elif '), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "pattern"}), tests="PATTERN_MATCH")
