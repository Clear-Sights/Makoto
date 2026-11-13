# Round "6.2.1": three changes to one map. Committed before any code or run; never edited after.

Owner, 2026-11-13: "yes, do 1 and 2", "and the gap".

## Diagnosis (post hoc on the one map run, fitted): 6.2.0's six failures
- **Two sigchange failures:** the model ran `pytest`, which passed, and 6.2.0 counts a test runner as reaching every file. The repository's tests do not reach every user of the changed function, and the unreached users were wrong.
- **Three unrun failures:** after the shadowing error the model deleted its new module and reverted. The program then ran clean and the final answer was admitted. No run-based check sees an abandoned goal.
- **One unrun failure:** no edit was made.
- **None** ended with a changed file unrun and not held.

## Changes
1. **A test run reaches what the tests reach.** A test runner with no program argument reaches the test files and everything they depend on through the map. It no longer reaches every file.
   - A test file is one whose name contains `test` or `spec`, or that lies under a folder named `test`, `tests`, `spec` or `__tests__`.
   - `make` and the package scripts (`npm`, `yarn`, `pnpm` with `run`, `test`, `start`) are treated the same way.
2. **The note repeats only for a new run.** After an edit, the note is given when the entry programs it names include one that no earlier note in the session named. Otherwise the edit gets no note. The hold is unchanged.
3. **Unquoted shell redirects make links.** In a shell file (extension `sh`, `bash` or `zsh`, or a shell shebang):
   - `> path`, `>> path` and `tee path` make a produced-by link;
   - `< path` makes a reads link;
   - the path must name a project file.

**Unchanged:** everything else in 6.2.0.

## Checks before the live run
- **Tests added:**
  - a passing `pytest` checks a module the tests import, and leaves a changed module no test reaches demanded;
  - twelve edits whose runs are all the same entry program give one note;
  - a new entry program gives a second note;
  - a shell script with `python3 gen.py > out.json` links `out.json` to the script.
- **6.2.0's tests** pass, changed only where they assert the old test-runner rule or one note per file.

## Live (Haiku, CLI 2.1.322)
- **Tasks:** 40 fresh tasks per family: unrun level 3, seeds 9700000001 to 9700000040; sigchange with 12 users, seeds 9710000001 to 9710000040.
- **Arms:** plain, 6.2.0 (one map, 8a5c7dc) and 6.2.1.
- **Kill test:** one call per family.

## Ship rule
- **6.2.1 ships** when all of these hold on each family:
  - it passes at least 6.2.0's count minus 4;
  - its cost ratio to plain is at most 6.2.0's plus 0.05.
- **Otherwise** the owner decides.

## Predictions
| id | quantity | point | range |
|---|---|---|---|
| V1 | unrun pass (of 40): plain; 6.2.0; 6.2.1 | 25; 36; 36 | 17 to 32; 29 to 40; 29 to 40 |
| V2 | sigchange pass: plain; 6.2.0; 6.2.1 | 25; 36; 37 | 16 to 32; 28 to 40; 28 to 40 |
| V3 | notes per run on sigchange: 6.2.0; 6.2.1 | 8.5; 2.0 | 6 to 11; 1 to 5 |
| V4 | cost ratio to plain, 6.2.1: unrun; sigchange | 1.33; 1.33 | 1.1 to 1.55; 1.1 to 1.6 |
| V5 | probability that the ship rule holds | 0.65 | |
