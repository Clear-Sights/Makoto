# Round "6.2.2": the note comes from the tree, not from the edit tools. Committed before any code or run; never edited after.

Owner, 2026-11-13: "Find out why on the caveat", then "Yes" to fixing and measuring it.

## Diagnosis (post hoc on the claims round, fitted)
- **Sonnet edits through the shell.** Under Sonnet no note ever fired, and every run was held once. Its runs are Bash calls only.
- **The cause:** 6.2.1 gives the note only after a completed Write, Edit, MultiEdit or NotebookEdit. The hold reads the tree, so it fired in every run.
- **The cost:** a thrown-away final answer and an extra turn per run, at 1.57 to 1.68 times plain's cost.

## Change
- **The note comes from the tree.** After every completed tool call, Makoto compares the tree with the map, as the hold does. It gives the note when the unchecked demanded set names an entry program that no earlier note named.
  - It no longer matters which tool made the change.
  - 6.2.1's once-per-new-run rule stays.
- **Unchanged:** everything else in 6.2.1.

## Checks before the live run
- **Tests added:**
  - a file changed by a Bash call (a redirect, and `sed -i`) gets the note after that call;
  - a Bash call that changes nothing gets none;
  - a run that checks the change gets none;
  - 6.2.1's note tests still pass.
- **Timing:** on a tree of 5,000 files, the PostToolUse hook takes under 0.5 s (measured, reported).

## Live (CLI 2.1.323)
- **Tasks:** 40 fresh tasks per cell. The families are unrun level 3 and sigchange with 12 users.

| model | family | seeds |
|---|---|---|
| Sonnet `claude-sonnet-5-5` | unrun | 9770000001 to 9770000040 |
| Sonnet | sigchange | 9780000001 to 9780000040 |
| Haiku `claude-haiku-5-5` | unrun | 9790000001 to 9790000040 |
| Haiku | sigchange | 9800000001 to 9800000040 |

- **Arms:** plain, 6.2.1 (main 9ee9979 plugin) and 6.2.2.
- **Kill test:** one 6.2.2 call per model.
- **Spend cap:** 40 USD.

## Ship rule
- **6.2.2 ships** when both of these hold in each of the four cells:
  - it passes at least 6.2.1's count minus 4;
  - its cost ratio to plain is at most 6.2.1's plus 0.05.
- **Otherwise** the owner decides.

## Predictions
| id | quantity | point | range |
|---|---|---|---|
| W1 | Sonnet unrun pass (of 40): plain; 6.2.1; 6.2.2 | 16; 37; 37 | 8 to 26; 30 to 40; 30 to 40 |
| W2 | Sonnet sigchange pass: plain; 6.2.1; 6.2.2 | 28; 39; 39 | 20 to 36; 33 to 40; 33 to 40 |
| W3 | Sonnet holds per run: 6.2.1; 6.2.2 | 1.0; 0.3 | 0.9 to 1.1; 0.05 to 0.8 |
| W4 | Sonnet cost ratio, 6.2.2: unrun; sigchange | 1.40; 1.35 | 1.15 to 1.7; 1.1 to 1.65 |
| W5 | Haiku pass, 6.2.2: unrun; sigchange | 35; 36 | 28 to 40; 28 to 40 |
| W6 | Haiku cost ratio, 6.2.2: unrun; sigchange | 1.33; 1.33 | 1.1 to 1.55; 1.1 to 1.6 |
| W7 | probability that the ship rule holds | 0.6 | |
