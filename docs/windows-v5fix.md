# Windows fixes for Makoto 5.0.0

The supplied Python 3.13 Windows log reports nine failures. The changes address
their product causes and correct the real-command tests' shell assumptions.

| Failure(s) | Cause | Change and evidence |
| --- | --- | --- |
| 1: package contents | `str(relative_path)` emits backslashes on Windows. | Package keys use `as_posix()`. A plant supplies `PureWindowsPath` relative paths to the real package builder. |
| 2: `/w/my report.txt` | Normalizing the output to backslashes loses the complete slash-spelled path used to exempt split lexical spans. | File identities use `/`; spaced output exemptions recognize both separators with the existing exact boundaries. A near miss with extra filename characters still holds. |
| 3–6: echo, printf, Python, mutation plus echo | PATH's Bash can be WSL without a distro; `python3` can also resolve outside the test interpreter. | The tests select Git Bash on Windows and quote the active Python executable. All four real commands still run and assert their returned output. A simulated Windows fixture verifies Git Bash selection. |
| 7: redirected mutator ledger keys | File keys inherited the hook host's separator. | Recorded identities select path semantics from the recorded drive/share and accept either separator, retaining canonical `/` keys. The existing redirect plant also passes with `ntpath` and Windows `os.sep`. |
| 8: failed real Python run | An unquoted backslash-containing executable loses characters through Bash tokenization; `python.exe` is not recognized as an interpreter. | The test records a quoted slash-spelled executable. Product program names accept both separators and `.exe`, preserving interpreter operand selection. A failed-run plant pays d; eval, help and a different script do not. |
| 9: executable on another drive | Edit aliases call `relpath` across drives; dependent writer references and spaced output exemptions have the same unsafe assumption. | A shared helper checks drive/share identity before `relpath`, omits unavailable relative/module forms, and keeps absolute references. A plant rejects any attempted cross-drive call, requires the executable run, then clears d after its response. |

The shared helpers are in `plugin/makoto2/paths.py`. Exact original-source name
witnesses remain byte-sensitive: separator normalization applies to file tracking
and output exemptions. A mixed-separator plant verifies both stale-reading
invalidation and preservation of the exact-name requirement.

Validation on Linux with Python 3.13:

- Unchanged suite: 782 passed.
- New plants before runtime fixes: 12 failed, 5 passed (the passing cases are controls).
- New plants after fixes: 17 passed.
- Complete suite after fixes: 799 passed, with no tests skipped, xfailed or deleted by these changes.
- The original failing name, redirect, failed-run and extensionless-executable
  tests also pass with product `os.path`/`os.sep` replaced by Windows semantics: 4 passed.
- devE: all 800 sessions replayed before and after using a copied grader with
  `PLUGIN = Path('/home/user/build/v5fix/plugin')`. Both totals are 330 present
  held, 18 absent held, and 452 four-question notes. Every session's held decision
  is unchanged.

Replay outputs, scores and the pre-fix plant log are retained in
`/home/user/build/v5fix-grade/`. Native Windows CI was not run from this Linux
workspace. The required no-loss check uses `e8032ec`, the committed `HEAD`, and
`NOLOSS.tsv`; its outcome is reported with the final result.
