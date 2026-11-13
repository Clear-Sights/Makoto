# Round "collect": results

**Measured**, except where marked post hoc.
- **Sources:** `data/ANALYSIS_COLLECT_haiku.json`, `data/ANALYSIS_COLLECT_sonnet.json` (`harness/analyze_collect.py`, committed before the runs), `data/haiku/live.ledger.jsonl.gz`, `data/sonnet/live.ledger.jsonl.gz`.
- **Runs:** the re-run of `AMEND_3.md`. CLI 2.1.323, `srt` 0.0.83. n 40 per cell per arm; 480 of 480 runs usable, 0 retried. The seeds are now fitted.
- **Builds:** 6.2.1 (main 25adb83) and collect at 42e5b5e, which is what PR #185 merged as 6.3.0 (main e00084b).

## Verdict
**The ship rule fails in both models. On the sigchange family collect passes fewer tasks than 6.2.1, and on Sonnet fewer than plain.** 6.3.0 was merged before this result, at the owner's word.

| cell | pass: plain; 6.2.1; collect | cost ratio to plain: 6.2.1; collect | holds per run: 6.2.1; collect | notes per run: 6.2.1; collect |
|---|---|---|---|---|
| Haiku, unrun | 26; 33; 34 | 1.23; 1.26 | 0.10; 0.13 | 0.98; 0.88 |
| Haiku, sigchange | 30; 40; 35 | 1.27; 1.01 | 0.90; 0 | 0.60; 0.65 |
| Sonnet, unrun | 21; 38; 39 | 1.42; 1.25 | 1.00; 0 | 0; 0.68 |
| Sonnet, sigchange | 37; 40; 29 | 1.55; 1.04 | 1.00; 0.03 | 0; 0.08 |

- **Where the rule fails** (collect passes at least 6.2.1's count minus 4, and costs less against plain than 6.2.1):
  - Haiku unrun, on cost: 1.255 against 1.233;
  - Haiku sigchange, on passes: 35 against a floor of 36;
  - Sonnet sigchange, on passes: 29 against a floor of 36.
  - Sonnet unrun meets it: 39 against 38, at 1.25 against 1.42.
- **Collect against 6.2.1, points [95 %]; discordant pairs:**
  - Haiku unrun +2.5 [−7.5, +12.5]; 2 to 3;
  - Haiku sigchange −12.5 [−22.5, −2.5]; 5 to 0; p 0.063;
  - Sonnet unrun +2.5 [−5.0, +12.5]; 1 to 2;
  - Sonnet sigchange −27.5 [−42.5, −15.0]; 11 to 0; p 0.001.
- **Collect against plain:**
  - Haiku unrun +20.0 [0.0, +37.5], p 0.077; Haiku sigchange +12.5 [−5.0, +30.0], p 0.27;
  - Sonnet unrun +45.0 [+30.0, +60.0], p below 0.0001, Holm rejects;
  - Sonnet sigchange −20.0 [−35.0, −5.0], p 0.039; discordant 10 to 2; Holm does not reject.
- **What collect did deliver:** the hold is gone (0 to 0.13 per run against 0.1 to 1.0), and on sigchange the cost is plain's (1.01, 1.04).

## Why sigchange loses (post hoc, from the trees and streams)
- **The probe's pass carries no knowledge of the change.**
  - The 16 failed collect runs on sigchange leave 24 wrong modules. Run as the probe runs them, 0 of the 24 fail.
  - A module there only defines functions. Running the file calls none of them, so it exits 0 whether its callers are right or wrong. The one test file covers only the changed function.
  - Makoto stamped every such file as checked, and admitted the final answer with nothing said: in 12 of the 16 failed runs it said nothing at all.
- **6.2.1's hold did the work there.** It stops the answer and names every unchecked file; the model then goes back, calls the functions, and finds the caller it missed. 40 of 40 on both models.
- **The assumption shown false:** that a program exiting 0 is a check of what changed in it. It is a read of the file's top level only.
- **Sonnet, collect below plain:** Makoto said something in 1 of the 11 failed runs, so no message of Makoto's explains the gap. It is unexplained, and Holm does not reject it.

## Predictions
| id | point (range) | measured | result |
|---|---|---|---|
| I1 Haiku pass, collect: unrun; sigchange | 35; 35 (28–40; 26–40) | 34; 35 | hit; hit |
| I2 Haiku cost ratio: unrun; sigchange | 1.15; 1.20 (1.0–1.35; 1.0–1.45) | 1.26; 1.01 | hit; hit |
| I3 Sonnet pass, collect: unrun; sigchange | 37; 38 (30–40; 30–40) | 39; 29 | hit; **MISS** (below) |
| I4 Sonnet cost ratio: unrun; sigchange | 1.20; 1.20 (1.0–1.45; 1.0–1.5) | 1.25; 1.04 | hit; hit |
| I5 holds per run: Haiku; Sonnet | 0.1; 0.3 (0–0.5; 0–0.8) | 0.06; 0.01 | hit; hit |
| I6 share of collect runs with no model run of Python after the last change | 0.6 (0.3–0.9) | about 0.45 (post hoc, by pattern match on commands; 72 of 160) | hit |
| I7 the ship rule holds: 0.45 | | no | the more likely side |

**I3 is the round's finding.** Its miss traces to the assumption above.

## What it means
- **The run is rightly Makoto's step where a run exercises the change:** unrun, where the entry program is the thing changed. There collect matches 6.2.1 with no hold, and on Sonnet costs 1.25 against 1.42.
- **It is wrong where the run exercises nothing:** a pass must count only for what the run actually executed.
- **Candidates (the owner chooses):**
  1. Revert main to 6.2.1.
  2. Keep the probe, and let a pass check a file only when the probe is a test, or an entry program that calls into it; a file whose run executes only definitions stays unchecked, and 6.2.1's hold covers it.
  3. Keep 6.3.0 as it is, with this limit stated.

## Spend
- Worker calls: kill tests 0.244 USD; first run, superseded, 1.451 USD (Haiku); re-run 10.301 USD (Haiku 1.275, Sonnet 9.026). Total **12.00 USD**, under the 40 USD cap.
- `data/haiku/SPEND_COLLECT.tsv` also holds the first run's rows (seeds 982… and 983…); the re-run's are seeds 987… and 988….
