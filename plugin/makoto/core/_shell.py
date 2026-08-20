"""Small shell-argv normalizer shared by command-evidence consumers.

This is deliberately not a Bash evaluator. It recognizes literal command segments, strips
transparent launch wrappers, and fails open on malformed syntax. Quoted prose, comments, and
arguments of unrelated programs never become executable evidence.
"""
from __future__ import annotations

import re
import shlex


_SHELL_SEPARATORS = frozenset({"|", "||", "&&", ";", "&", "\n"})
_ASSIGNMENT_RX = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
_DIRECT_TEST_RUNNERS = frozenset({
    "pytest", "py.test", "nox", "tox", "jest", "vitest", "mocha", "ava", "jasmine",
    "rspec", "phpunit", "ctest",
})


def _effective_argv(argv):
    """Strip leading assignments and transparent launch wrappers; preserve option argv."""
    argv = list(argv)
    while argv and _ASSIGNMENT_RX.fullmatch(argv[0]):
        argv.pop(0)
    while argv and argv[0].rsplit("/", 1)[-1] in {"command", "nohup", "sudo", "env"}:
        wrapper = argv.pop(0).rsplit("/", 1)[-1]
        while argv and (argv[0].startswith("-") or _ASSIGNMENT_RX.fullmatch(argv[0])):
            # env/sudo options with separate values are intentionally outside this small parser.
            argv.pop(0)
        if wrapper not in {"env", "sudo"}:
            break
    return argv


def _shell_segments(command: str):
    """Return ``[(argv, following_operator)]`` for literal shell command segments."""
    try:
        lexer = shlex.shlex(command or "", posix=True, punctuation_chars="|;&<>\n")
        lexer.whitespace_split = True
        lexer.commenters = "#"
        lexer.whitespace = " \t\r"
        tokens = list(lexer)
    except (TypeError, ValueError):
        return []
    segments, current = [], []
    for token in tokens:
        if token in _SHELL_SEPARATORS:
            if current:
                segments.append((current, token))
                current = []
        else:
            current.append(token)
    if current:
        segments.append((current, ""))

    # Preserve real commands passed to a shell/ssh as one quoted argument without scanning
    # arbitrary quoted arguments of unrelated programs.
    nested = []
    for argv, _operator in segments:
        effective = _effective_argv(argv)
        if effective and effective[0].rsplit("/", 1)[-1] in {"ssh", "sh", "bash", "zsh"}:
            for arg in effective[1:]:
                if any(ch.isspace() for ch in arg):
                    nested.extend(_shell_segments(arg))
    return segments + nested


def _git_subcommand(argv):
    args = list(argv[1:])
    while args:
        if args[0] in {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}:
            args = args[2:]
        elif args[0].startswith(("--git-dir=", "--work-tree=", "--namespace=")):
            args.pop(0)
        elif args[0].startswith("-"):
            args.pop(0)
        else:
            return args[0], args[1:]
    return "", []


def _test_target(args) -> bool:
    return any(a == "test" or a.startswith(("test:", "test-", "test_")) for a in args)


def _is_test_argv(raw_argv) -> bool:
    """True only when the effective executable/argv invokes a recognized test runner."""
    argv = _effective_argv(raw_argv)
    if not argv:
        return False
    program = argv[0].rsplit("/", 1)[-1]
    args = argv[1:]
    if program in _DIRECT_TEST_RUNNERS:
        return True
    if program == "rails":
        return _test_target(args)
    if re.fullmatch(r"python[0-9.]*", program):
        if any(a == "-m" and b in {"pytest", "unittest"} for a, b in zip(args, args[1:])):
            return True
        return any(a.lstrip("./") in {
            "scripts/falsify.py", "scripts/cert.py", "scripts/connectivity.py",
            "measure_corpus_fp.py",
        } for a in args)
    if program in {"go", "cargo"}:
        return "test" in args or (program == "cargo" and "nextest" in args)
    if program in {"npm", "yarn", "pnpm", "make", "just", "mvn"}:
        return _test_target(args)
    if program in {"gradle", "gradlew"}:
        return _test_target(args)
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
    if not argv or argv[0].rsplit("/", 1)[-1] != "git":
        return False
    subcommand, args = _git_subcommand(argv)
    if subcommand != "push":
        return False
    for arg in args:
        if arg == "--dry-run" or arg.startswith("--dry-run="):
            return False
        if re.fullmatch(r"-[A-Za-z]+", arg) and "n" in arg[1:]:
            return False
    return True


def _command_runs_tests(command: str) -> bool:
    return any(_is_test_argv(argv) for argv, _operator in _shell_segments(command))


def _command_pushes_git(command: str) -> bool:
    return any(_is_git_push_argv(argv) for argv, _operator in _shell_segments(command))
