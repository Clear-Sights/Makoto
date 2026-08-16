# 0038: Shared detector-engine helpers extracted to `_stdlib_ast_helpers`

Date: 2026-07-09

## Relocated design history

From `makoto/checks/hollowTest.py`, above `_is_assertion_call()`:

```text
_callee_chain imported at module top from _stdlib_ast_helpers (2026-07-09: was a local duplicate
of both deadPureStatement.py's usage pattern and lib/factories.py::callee_chain; extracted rather
than left duplicated -- see tests/test_detector_engines_are_stdlib_isolated.py).
```

From the same file's Stop-hook adapter header, and its `_run()`:

```text
_is_scratch/_read (imported at module top from _stdlib_ast_helpers) are shared verbatim with
deadPureStatement.py (2026-07-09: found alpha-equivalent by AST canonicalization; extracted
rather than left duplicated -- see tests/test_detector_engines_are_stdlib_isolated.py).

iteration scaffold (touched -> .py -> cwd-anchor -> scratch-skip -> read) shared with
deadPureStatement._run via the stdlib-isolated helper home -- 2026-07-09 dedup round 2
```
