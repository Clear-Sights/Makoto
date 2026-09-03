"""The hook path imports nothing that exists on only one OS, and the check that says so has teeth.

THE INCIDENT. A live dispatch reported, on every single call:

    PostToolUse:Bash says: makoto: 1 check-evaluation fault(s) on this call -- [exception]
    ledger update failed: ModuleNotFoundError: No module named 'fcntl'. The call was ALLOWED
    WITHOUT BEING CHECKED (fail-open). See dispatch_errors.jsonl in the makoto state dir.

The fail-open is correct and deliberate, exactly as in `test_encoding_is_stated.py`. The DEFECT is
the crash. `fcntl` is Unix-only; `plugin/makoto/state/ledger.py` imported it at module scope for
the one `flock` that guards the chain against concurrent appends. On Windows the import raised, so
EVERY ledger update raised, so every gate fell open. Not one check ran, on that OS, ever.

WHY THIS IS WORSE THAN THE ENCODING INCIDENT. That one needed a curly quote in a file a check
happened to read -- rare, per-call, recoverable. This one is unconditional: it fires at import, on
the first call and every call after it. The user sees a fault notice rather than silence, which is
the fail-open working as designed, but the coverage is total zero.

WHY A LAW AND NOT ONE EDIT. The crash named one module. Parsed rather than grepped, `plugin/` held
exactly ONE Unix-only import -- so unlike the encoding incident there were no twins waiting. That
is a measured result, not an assumption, and this law is what keeps it measured: the next
`import pwd` or `os.fork` on the hook path fails here instead of on a user's machine.

SCOPE, STATED. This law covers `plugin/` -- the code that runs inside the host's hook, where an
import error costs every check on a platform nobody tested. Developer entrypoints outside
`plugin/` are not covered: there a crash is immediate and loud to the person who ran it. Widening
this law to them is a separate change with a separate argument, not an oversight.

WHAT IS NOT CLAIMED. Passing this law does not make makoto Windows-CERTIFIED. It proves the hook
path carries no Unix-only import and that the lock has a real Windows backend. The msvcrt branch
is exercised here by injection, not by a Windows kernel -- so its argument-level contract is
established and its behaviour under real contention on Windows remains untested. Said plainly
rather than implied by a green run.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import pathlib
import sys
import types
import unittest

PLUGIN = pathlib.Path(__file__).resolve().parent.parent / "plugin"

# Unix-only stdlib modules: absent on Windows, so an unguarded import of one is a platform crash.
UNIX_ONLY_MODULES = {
    "fcntl", "pwd", "grp", "termios", "tty", "pty", "resource",
    "posix", "syslog", "crypt", "nis", "spwd",
}
# Unix-only `os` attributes: present as names, AttributeError on Windows.
UNIX_ONLY_OS_ATTRS = {
    "fork", "forkpty", "getuid", "geteuid", "setuid", "setsid", "setpgrp",
    "getpgid", "killpg", "uname", "wait3", "wait4", "WIFEXITED", "WEXITSTATUS",
}


def _guarded(node: ast.AST, tree: ast.Module) -> bool:
    """True when `node` sits inside a try/except that catches ImportError.

    A guarded import is the fix, not the defect -- this law must not flag its own remedy.
    """
    for parent in ast.walk(tree):
        if not isinstance(parent, ast.Try):
            continue
        if not any(
            handler.type is None
            or (isinstance(handler.type, ast.Name) and handler.type.id in ("ImportError", "Exception"))
            for handler in parent.handlers
        ):
            continue
        for body_node in parent.body:
            for descendant in ast.walk(body_node):
                if descendant is node:
                    return True
    return False


def unportable_sites(root: pathlib.Path) -> list[str]:
    """Every unguarded Unix-only import or `os.<posix-attr>` use under `root`.

    Parsed, never grepped: a grep cannot tell an import inside a try/except ImportError from a
    bare one, and cannot tell `os.fork` from the word "fork" in a comment. Both distinctions
    decide whether a site is a defect or its fix.
    """
    found = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            hit = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in UNIX_ONLY_MODULES:
                        hit = f"import {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in UNIX_ONLY_MODULES:
                    hit = f"from {node.module}"
            elif isinstance(node, ast.Attribute):
                if (isinstance(node.value, ast.Name) and node.value.id == "os"
                        and node.attr in UNIX_ONLY_OS_ATTRS):
                    hit = f"os.{node.attr}"
            if hit and not _guarded(node, tree):
                found.append(f"{path.relative_to(root)}:{node.lineno} {hit}")
    return found


class TheHookPathRunsOnEitherOS(unittest.TestCase):
    def test_no_plugin_module_imports_a_unix_only_module_unguarded(self):
        unportable = unportable_sites(PLUGIN)
        self.assertEqual(unportable, [], "unguarded Unix-only use under plugin/: "
                                         + "; ".join(unportable))

    def test_the_check_can_fail(self):
        """NON-VACUITY. A law that scans a tree can pass because it found nothing to scan."""
        import tempfile
        with tempfile.TemporaryDirectory() as name:
            root = pathlib.Path(name)
            (root / "clean.py").write_text(
                "try:\n    import fcntl\nexcept ImportError:\n    fcntl = None\n", encoding="utf-8")
            self.assertEqual(unportable_sites(root), [],
                             "a guarded import is the remedy and must not be flagged")
            (root / "dirty.py").write_text("import fcntl\n", encoding="utf-8")
            self.assertEqual(len(unportable_sites(root)), 1, "a bare `import fcntl` must be flagged")
            (root / "attr.py").write_text("import os\nos.fork()\n", encoding="utf-8")
            self.assertEqual(len(unportable_sites(root)), 2, "a bare os.fork() must be flagged")


class TheIncidentReproduced(unittest.TestCase):
    """The actual fault: import the ledger with `fcntl` unavailable, as Windows has it."""

    def _import_ledger_without_fcntl(self):
        """Re-import `makoto.state.ledger` as a Windows interpreter would: no `fcntl`, but a real
        `msvcrt`. Then restore.

        BOTH halves are needed and the first draft of this helper had only one. Supplying "no
        fcntl" alone does not simulate Windows on a Linux host -- it simulates a platform with
        NEITHER lock backend, where the `except ImportError` branch re-raises on `import msvcrt`
        and the test fails for a reason no user will ever hit. The stub is what makes this
        Windows rather than nowhere.
        """
        real_import = builtins.__import__

        stub = types.ModuleType("msvcrt")
        stub.LK_LOCK, stub.LK_NBLCK, stub.LK_UNLCK = 1, 2, 0
        stub.locking = lambda fileno, mode, nbytes: None

        def windows_imports(name, *args, **kwargs):
            if name == "fcntl":
                raise ModuleNotFoundError("No module named 'fcntl'")
            return real_import(name, *args, **kwargs)

        saved = {k: v for k, v in sys.modules.items() if k.startswith("makoto.state.ledger")}
        saved_msvcrt = sys.modules.get("msvcrt")
        for key in saved:
            del sys.modules[key]
        sys.modules.pop("fcntl", None)
        sys.modules["msvcrt"] = stub
        builtins.__import__ = windows_imports
        try:
            return importlib.import_module("makoto.state.ledger")
        finally:
            builtins.__import__ = real_import
            if saved_msvcrt is None:
                sys.modules.pop("msvcrt", None)
            else:
                sys.modules["msvcrt"] = saved_msvcrt
            for key in list(sys.modules):
                if key.startswith("makoto.state.ledger"):
                    del sys.modules[key]
            sys.modules.update(saved)
            importlib.import_module("makoto.state.ledger")

    def test_the_ledger_imports_when_fcntl_is_unavailable(self):
        module = self._import_ledger_without_fcntl()
        self.assertIsNone(module.fcntl, "the fcntl backend must be absent in this configuration")
        self.assertIsNotNone(module.msvcrt, "the msvcrt backend must be selected in its place")

    def test_the_windows_backend_locks_byte_zero_exclusively_and_releases_before_close(self):
        """The msvcrt path's contract, asserted at argument level.

        Byte 0 specifically: `msvcrt.locking` locks from the CURRENT position, so two appenders
        that did not seek would hold disjoint regions and both proceed -- forking the chain the
        lock exists to protect. This asserts the seek, the exclusive non-blocking mode, and that
        the release happens while the handle is still open.
        """
        module = self._import_ledger_without_fcntl()

        calls = []

        class FakeMsvcrt:
            LK_NBLCK, LK_UNLCK = 2, 0

            def locking(self, fileno, mode, nbytes):
                calls.append((mode, nbytes, handle.tell(), handle.closed))

        class FakeHandle:
            closed = False

            def __init__(self):
                self._pos = 4096  # opened "a+", so the position starts at end-of-file

            def seek(self, pos):
                self._pos = pos

            def tell(self):
                return self._pos

            def fileno(self):
                return 3

        handle = FakeHandle()
        saved_msvcrt = module.msvcrt
        module.msvcrt = FakeMsvcrt()
        try:
            module._lock_exclusive(handle)
            module._unlock(handle)
        finally:
            module.msvcrt = saved_msvcrt

        self.assertEqual(
            calls,
            [(FakeMsvcrt.LK_NBLCK, 1, 0, False), (FakeMsvcrt.LK_UNLCK, 1, 0, False)],
            "expected an exclusive lock then an unlock, each on one byte at position 0, "
            "both while the handle is open",
        )

    def test_the_windows_backend_waits_for_a_held_lock_rather_than_failing(self):
        """Contention must block, not raise: a busy sidecar is the normal case, not an error."""
        module = self._import_ledger_without_fcntl()

        attempts = []

        class BusyThenFree:
            LK_NBLCK, LK_UNLCK = 2, 0

            def locking(self, fileno, mode, nbytes):
                attempts.append(mode)
                if len(attempts) < 3:
                    raise OSError(36, "Resource deadlock avoided")

        class FakeHandle:
            def seek(self, pos): pass
            def fileno(self): return 3

        saved_msvcrt = module.msvcrt
        module.msvcrt = BusyThenFree()
        try:
            module._lock_exclusive(FakeHandle())
        finally:
            module.msvcrt = saved_msvcrt

        self.assertEqual(len(attempts), 3, "must retry a busy lock until it is free")


if __name__ == "__main__":
    unittest.main()
