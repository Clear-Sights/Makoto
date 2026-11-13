# Round "testwait": a failing test is reported at the final answer, not mid-change. Committed before any code or run; never edited after.

Owner, 2026-11-13: "Do 2 and merge if it holds, also frankly haiku isn't the primary use case".
- **Finding it starts from:** `research/quiet/RESULTS.md`. A probe after each tool call reports the project's own test failing while the model is still changing what the test covers. On Haiku sigchange that cost three turns per run.
- **Why not "the same failure twice running"** (the candidate named in quiet's results): worked through before any code, it cannot help. The test keeps failing with the same output through every later edit, so the second read comes one tool call after the first and the note is sent all the same.
- **Principle (the owner's Immediacy, far side):** do not assume what can change has not. A test states what the code did before the change; while the change is in progress its failure is expected, and only at the final answer is it a finding.

## The change (on quiet, a503ac4)
- **One condition:** after a tool call, a probe's failure is noted only when the failing entry program is not a test file (the map's existing test pattern: a name containing `test` or `spec`, or a file under `test`, `tests`, `spec` or `__tests__`).
- **At the final answer nothing changes:** the hold carries every failure, a test's included.
- **Nothing else changes.** No new state, setting or mechanism; the rule names no language, runner or task.

## Checks before the live run
- **Tests** (with `srt`):
  - a failing test file gives no note after a tool call, and its failure is in the hold;
  - a failing program that is not a test is noted after the tool call, as before;
  - quiet's other tests pass unchanged.
- **Kill test:** one call per model on sigchange and on unrun.

## Live (CLI 2.1.323; `srt` 0.0.83)
| model | family | seeds |
|---|---|---|
| Haiku | unrun level 3 | 10020000001 to 10020000040 |
| Haiku | sigchange, 12 users | 10030000001 to 10030000040 |
| Sonnet | unrun level 3 | 10040000001 to 10040000040 |
| Sonnet | sigchange, 12 users | 10050000001 to 10050000040 |

- **Arms:** plain, 6.2.1 (main 82fc0aa) and testwait. In the data the testwait arm is named `collect`; the harness is `research/observed/harness/live_collect.py`, unchanged, and the analysis is `harness/analyze_testwait.py` (observed's with this round's rule parts).
- **Spend cap:** 25 USD.
- **Fitted:** unrun and sigchange are fitted families, and this rule was chosen from sigchange; the result proves these families and no more.

## Ship rule
The owner's word sets the weight: Haiku is not the primary use case.
- **Sonnet, both cells:**
  - it passes at least 6.2.1's count minus 4;
  - its cost ratio to plain is at most 6.2.1's plus 0.05;
  - in at least one Sonnet cell its cost ratio is below 6.2.1's.
- **Haiku, both cells:**
  - it passes at least 6.2.1's count minus 4;
  - its cost ratio to plain is at most 6.2.1's plus 0.10. (At n 40, Haiku sigchange's cost interval is about ±0.15, so two arms that behave alike miss a 0.05 ceiling about one time in three.)
- **If all hold, testwait is merged** (the owner's word). Otherwise main stays 6.2.1.

## Predictions
| id | quantity | point | range |
|---|---|---|---|
| T1 | Haiku pass, testwait: unrun; sigchange (of 40) | 34; 38 | 28 to 40; 34 to 40 |
| T2 | Haiku cost ratio, testwait: unrun; sigchange | 1.24; 1.25 | 1.05 to 1.45; 1.05 to 1.5 |
| T3 | Sonnet pass, testwait: unrun; sigchange | 38; 40 | 33 to 40; 36 to 40 |
| T4 | Sonnet cost ratio, testwait: unrun; sigchange | 1.22; 1.52 | 1.05 to 1.45; 1.35 to 1.68 |
| T5 | notes per run, testwait, Haiku sigchange | 0.6 | 0.3 to 1.0 |
| T6 | holds per run, testwait, Sonnet: unrun; sigchange | 0.05; 1.0 | 0 to 0.4; 0.8 to 1.0 |
| T7 | probability that the ship rule holds | 0.6 | |
