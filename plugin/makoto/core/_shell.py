"""Small shell-argv normalizer shared by command-evidence consumers.

This is deliberately not a Bash evaluator. It recognizes literal command segments, strips
transparent launch wrappers, and fails open on malformed syntax. Quoted prose, comments, and
arguments of unrelated programs never become executable evidence.
"""
from __future__ import annotations

import re
import shlex


_SHELL_SEPARATORS = frozenset({"|", "||", "&&", ";", "&", "\n"})
# DOTALL: an assignment VALUE carrying a newline (A="1\n2") is still one assignment word,
# not the segment's program.
_ASSIGNMENT_RX = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.DOTALL)
_DIRECT_TEST_RUNNERS = frozenset({
    "pytest", "py.test", "nox", "tox", "jest", "vitest", "mocha", "ava", "jasmine",
    "rspec", "phpunit", "ctest",
})
# Runners whose test intent lives in a target word (`npm test`, `yarn test:ci`, ...), split by
# WHERE that word may legally sit: package runners take one command word in the subcommand slot
# (a test-shaped word elsewhere -- `npm install --save-dev test-utils` -- is an argument, not
# intent), while build runners take a list of positional goals/targets (`make lint test`,
# `mvn clean test`), any of which may be the test one.
_SUBCOMMAND_TARGET_RUNNERS = frozenset({"rails", "npm", "yarn", "pnpm"})
_MULTI_TARGET_RUNNERS = frozenset({"make", "just", "mvn", "gradle", "gradlew"})
_TEST_TARGET_RUNNERS = _SUBCOMMAND_TARGET_RUNNERS | _MULTI_TARGET_RUNNERS
_LAUNCH_WRAPPERS = frozenset({
    "command", "nohup", "sudo", "env", "timeout", "time", "stdbuf", "xargs",
})
# `timeout` interposes a positional DURATION between itself and the launched program.
_TIMEOUT_DURATION_RX = re.compile(r"\d+(?:\.\d+)?[smhd]?")
_NESTED_SHELL_PROGRAMS = frozenset({"ssh", "sh", "bash", "zsh"})
_GIT_VALUED_OPTIONS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
_SUDO_VALUED_OPTIONS = frozenset({"-u", "-g", "-h", "-p", "-r", "-t", "-C",
                                  "--user", "--group", "--host", "--prompt", "--role",
                                  "--type", "--close-from"})
_PYTHON_RX = re.compile(r"python[0-9.]*")
_SHORT_FLAG_RX = re.compile(r"-[A-Za-z]+")


def _basename(word: str) -> str:
    """Trailing path component of an argv word (``/usr/bin/git`` -> ``git``)."""
    return word.rsplit("/", 1)[-1]


def _effective_argv(argv):
    """Strip leading assignments and transparent launch wrappers; preserve option argv.

    Every wrapper may be followed by another wrapper -- `nohup sudo prog` and `sudo nohup prog`
    are the same launch, so evidence must not depend on wrapper ORDER (the old asymmetric
    break made the first read as no launch at all)."""
    argv = list(argv)
    while argv and _ASSIGNMENT_RX.fullmatch(argv[0]):
        argv.pop(0)
    while argv and _basename(argv[0]) in _LAUNCH_WRAPPERS:
        wrapper = _basename(argv.pop(0))
        while argv and (argv[0].startswith("-") or _ASSIGNMENT_RX.fullmatch(argv[0])):
            option = argv.pop(0)
            # Wrapper options such as ``sudo -u bob`` consume the following word too.  Leaving
            # that value at argv[0] makes it masquerade as the launched program and loses the
            # command evidence that follows it.
            if wrapper == "sudo" and option in _SUDO_VALUED_OPTIONS and argv:
                argv.pop(0)
        if wrapper == "timeout" and argv and _TIMEOUT_DURATION_RX.fullmatch(argv[0]):
            argv.pop(0)
    return argv


# A run of control-operator punctuation shlex groups into one token that is not in
# `_SHELL_SEPARATORS` (``|&``, ``;;``, ...). Bash treats these as operators, never argv words,
# so they must SEPARATE segments rather than glue two commands into one argv. Redirection
# punctuation (anything with ``<``/``>``) deliberately stays inside the argv as before.
_CONTROL_RUN_RX = re.compile(r"[|;&]+")
# A leading command-substitution word -- ``$(prog`` or ``name=$(prog`` (backtick form too;
# ``$((`` arithmetic excluded). Only consulted at a segment's HEAD, where the substitution IS
# the segment's own command and its exit status is the statement's.
_HEAD_SUBSTITUTION_RX = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_]*=)?(?:\$\((?!\()|`)")


def _normalize_segment_argv(argv):
    """Dissolve grouping/substitution punctuation glued onto a segment's real words.

    Standalone ``(`` / ``)`` subshell delimiters are dropped and glued ones stripped from the
    first/last word, so ``( pytest -q )`` and ``(pytest -q)`` both expose ``pytest``. A HEAD
    command-substitution word loses its wrapper (``out=$(pytest -q)`` runs pytest; the
    assignment's exit is the substitution's). A substitution buried in a later argument of an
    unrelated program is deliberately left alone -- scanning it would need the consumer-visible
    nested-segment boundary to move too."""
    argv = [t for t in argv if t not in ("(", ")")]
    if not argv:
        return argv
    m = _HEAD_SUBSTITUTION_RX.match(argv[0])
    if m and len(argv[0]) > m.end():
        argv[0] = argv[0][m.end():]
        closer = "`" if m.group(0).endswith("`") else ")"
        for i, tok in enumerate(argv):
            if tok.endswith(closer):
                argv[i] = tok[: -1]
                break
    if argv[0].startswith("("):
        argv[0] = argv[0].lstrip("(")
    if argv and argv[-1].endswith(")"):
        argv[-1] = argv[-1].rstrip(")")
    return [t for t in argv if t]


def _shell_segments(command: str):
    """Return ``[(argv, following_operator)]`` for literal shell command segments."""
    try:
        lexer = shlex.shlex(command or "", posix=True, punctuation_chars="|;&<>\n")
        lexer.whitespace_split = True
        # Bash starts a comment only at WORD start; shlex's built-in commenters cut the line
        # from a ``#`` ANYWHERE (``--format=%h#%s`` lost the rest of the line, including a
        # following statement). Whole-token ``#...`` comments are recognized in the loop below.
        lexer.commenters = ""
        lexer.whitespace = " \t\r"
        tokens = list(lexer)
    except (TypeError, ValueError):
        return []
    segments, current = [], []

    def close_segment(operator):
        argv = _normalize_segment_argv(current)
        if argv:
            segments.append((argv, operator))
        current.clear()

    pending_heredocs = []   # delimiters announced by ``<<`` on the current line, in order
    active_heredoc = None   # delimiter that ends the body currently being skipped
    suppress_bodies = True  # False when the line's own command is a shell (the body IS code)
    expect_delimiter = False
    in_comment = False
    at_line_start = True
    for i, token in enumerate(tokens):
        newline = token == "\n"
        if active_heredoc is not None:
            # Here-doc BODY: data fed to a non-shell command, never statements of this shell
            # (prose must not become executable evidence). Ends at the delimiter standing
            # alone at line start; an unterminated body skips to the end -- fail open.
            if at_line_start and token == active_heredoc and (
                    i + 1 >= len(tokens) or tokens[i + 1] == "\n"):
                active_heredoc = pending_heredocs.pop(0) if pending_heredocs else None
            at_line_start = newline
            continue
        at_line_start = newline
        if in_comment:
            if not newline:
                continue
            in_comment = False
        elif token.startswith("#") and not newline:
            in_comment = True          # word-start comment: drop the rest of the line
            continue
        if expect_delimiter and not newline and token not in _SHELL_SEPARATORS:
            pending_heredocs.append(token)
            expect_delimiter = False
            current.append(token)      # the delimiter word stays in the argv, as before
            if _basename((_effective_argv(current) or [""])[0]) in _NESTED_SHELL_PROGRAMS:
                # ``bash <<EOF`` executes its body: keep the historical inline lexing so that
                # evidence inside it stays visible to consumers.
                suppress_bodies = False
            continue
        if token == "<<":
            expect_delimiter = True
            current.append(token)
            continue
        if token in _SHELL_SEPARATORS or _CONTROL_RUN_RX.fullmatch(token):
            close_segment(token)
            if newline and pending_heredocs:
                if suppress_bodies:
                    active_heredoc = pending_heredocs.pop(0)
                else:
                    pending_heredocs.clear()
                suppress_bodies = True
        else:
            current.append(token)
    close_segment("")

    # Preserve real commands passed to a shell/ssh as one quoted argument without scanning
    # arbitrary quoted arguments of unrelated programs.
    expanded = []
    for argv, operator in segments:
        effective = _effective_argv(argv)
        if effective and _basename(effective[0]) in _NESTED_SHELL_PROGRAMS:
            program = _basename(effective[0])
            command = None
            if program == "ssh":
                positional = [arg for arg in effective[1:] if not arg.startswith("-")]
                if len(positional) > 1:
                    command = " ".join(positional[1:])
            elif "-c" in effective[1:]:
                pos = effective.index("-c", 1)
                if pos + 1 < len(effective):
                    command = effective[pos + 1]
            if command is None:
                expanded.append((argv, operator))
                continue
            # ``bash -c pytest`` is as much a shell invocation as the quoted form; the
            # old whitespace gate silently missed it.  Splice nested segments *here*, not
            # after all outer segments, so the outer control operator remains adjacent to
            # the command it controls.
            nested = _shell_segments(command)
            if nested:
                nested[-1] = (nested[-1][0], operator)
                expanded.extend(nested)
            else:
                expanded.append((argv, operator))
        else:
            expanded.append((argv, operator))
    return expanded


def _git_subcommand(argv):
    args = list(argv[1:])
    while args:
        if args[0] in _GIT_VALUED_OPTIONS:
            args = args[2:]
        elif args[0].startswith("-"):
            # Covers the ``--git-dir=...`` glued forms too: value and flag are one word.
            args.pop(0)
        else:
            return args[0], args[1:]
    return "", []


def _is_test_target_word(word: str) -> bool:
    return word == "test" or word.startswith(("test:", "test-", "test_"))


def _test_target(program: str, args) -> bool:
    """Test intent read from the slot the runner actually consults -- the subcommand word for
    package runners, any positional goal for build runners -- never from arbitrary arguments."""
    positional = [a for a in args if not a.startswith("-")]
    if program in _MULTI_TARGET_RUNNERS:
        return any(_is_test_target_word(a) for a in positional)
    if not positional:
        return False
    if _is_test_target_word(positional[0]):
        return True
    return positional[0] in {"run", "run-script"} and len(positional) > 1 \
        and _is_test_target_word(positional[1])


def _is_test_argv(raw_argv) -> bool:
    """True only when the effective executable/argv invokes a recognized test runner."""
    argv = _effective_argv(raw_argv)
    if not argv:
        return False
    program = _basename(argv[0])
    args = argv[1:]
    if program in _DIRECT_TEST_RUNNERS:
        return True
    if program in _TEST_TARGET_RUNNERS:
        return _test_target(program, args)
    if _PYTHON_RX.fullmatch(program):
        if any(a == "-m" and b in {"pytest", "unittest"} for a, b in zip(args, args[1:])):
            return True
        return any(a.lstrip("./") in {
            "scripts/falsify.py", "scripts/cert.py", "scripts/connectivity.py",
            "measure_corpus_fp.py",
        } for a in args)
    if program in {"go", "cargo"}:
        return "test" in args or (program == "cargo" and "nextest" in args)
    if program == "npx":
        nested = [a for a in args if not a.startswith("-")]
        return bool(nested) and _is_test_argv(nested)
    if program in {"poetry", "uv", "pdm", "hatch"} and "run" in args:
        return _is_test_argv(args[args.index("run") + 1:])
    return argv[0].lstrip("./") in {
        "scripts/falsify", "scripts/cert", "scripts/connectivity", "measure_corpus_fp",
    }


def _is_git_push_argv(raw_argv) -> bool:
    """True only for a real, non-dry-run ``git push`` argv."""
    argv = _effective_argv(raw_argv)
    if not argv or _basename(argv[0]) != "git":
        return False
    subcommand, args = _git_subcommand(argv)
    if subcommand != "push":
        return False
    for arg in args:
        if arg == "--dry-run" or arg.startswith("--dry-run="):
            return False
        if _SHORT_FLAG_RX.fullmatch(arg) and "n" in arg[1:]:
            return False
    return True


def _command_runs_tests(command: str) -> bool:
    return any(_is_test_argv(argv) for argv, _operator in _shell_segments(command))


def _command_pushes_git(command: str) -> bool:
    return any(_is_git_push_argv(argv) for argv, _operator in _shell_segments(command))
