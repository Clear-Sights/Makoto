# Round "quiet": with nothing to report, the note follows only the edit tools. Committed before any code or run; never edited after.

Owner, 2026-11-13: "Run it and merge if it holds".
- **Finding it starts from:** `research/observed/RESULTS.md`. Observed matches 6.2.1's passes in every cell and failed its rule on one cost: Sonnet sigchange, 1.63 against 1.49. There Sonnet gets one note per run after a shell-made change, ignores it, and is held anyway.

## The change (on observed, 0e26d1a)
- **One condition removed:** the plain note ("Not run since a change…") follows only the edit tools, with or without the sandbox, as in 6.2.1.
- **A probe's failure is still noted after any tool call,** once per distinct output: that note carries something the model does not have.
- **Nothing else changes.** No new state, setting or mechanism; the rule names no language, runner or task.

## Checks before the live run
- **Tests** (with `srt`):
  - after a shell-made change whose probe prints nothing, there is no note, and the final answer is held once;
  - after a shell-made change whose probe fails, the note carries the failure;
  - after an edit-tool change whose probe prints nothing, the note is sent as before;
  - observed's other tests pass unchanged.
- **Kill test:** one call per model on sigchange and on unrun.

## Live (CLI 2.1.323; `srt` 0.0.83)
| model | family | seeds |
|---|---|---|
| Haiku | unrun level 3 | 9970000001 to 9970000040 |
| Haiku | sigchange, 12 users | 9980000001 to 9980000040 |
| Sonnet | unrun level 3 | 9990000001 to 9990000040 |
| Sonnet | sigchange, 12 users | 10000000001 to 10000000040 |

- **Arms:** plain, 6.2.1 (main 82fc0aa) and quiet. In the data the quiet arm is named `collect`: the harness is `research/observed/harness/live_collect.py` and the analysis `research/observed/harness/analyze_observed.py`, both unchanged.
- **Spend cap:** 25 USD.
- **Fitted:** unrun and sigchange are fitted families; the result proves these families and no more.

## Ship rule (observed's, unchanged)
- **quiet ships** when all of these hold:
  - in each of the four cells it passes at least 6.2.1's count minus 4;
  - in each of the four cells its cost ratio to plain is at most 6.2.1's plus 0.05;
  - in at least one cell its cost ratio to plain is below 6.2.1's.
- **If it holds, it is merged** (the owner's word, above). Otherwise main stays 6.2.1.

## Predictions
| id | quantity | point | range |
|---|---|---|---|
| Q1 | Haiku pass, quiet: unrun; sigchange (of 40) | 34; 38 | 28 to 40; 34 to 40 |
| Q2 | Haiku cost ratio, quiet: unrun; sigchange | 1.25; 1.27 | 1.05 to 1.45; 1.05 to 1.55 |
| Q3 | Sonnet pass, quiet: unrun; sigchange | 39; 40 | 33 to 40; 36 to 40 |
| Q4 | Sonnet cost ratio, quiet: unrun; sigchange | 1.33; 1.50 | 1.1 to 1.5; 1.35 to 1.65 |
| Q5 | notes per run, quiet, Sonnet sigchange | 0 | 0 to 0.2 |
| Q6 | holds per run, quiet, Sonnet: unrun; sigchange | 0.05; 1.0 | 0 to 0.4; 0.8 to 1.0 |
| Q7 | probability that the ship rule holds | 0.5 | |

- **Why Q7 is no higher:** on sigchange quiet should behave exactly as 6.2.1, and two arms that behave alike can still differ by more than 0.05 in cost at n 40 (Haiku sigchange's interval is about ±0.15).
