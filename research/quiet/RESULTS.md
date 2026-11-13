# Round "quiet": results

**Measured**, except where marked post hoc.
- **Sources:** `data/ANALYSIS_QUIET_haiku.json`, `data/ANALYSIS_QUIET_sonnet.json` (`research/observed/harness/analyze_observed.py`, unchanged), `data/*/live.ledger.jsonl.gz`.
- **Runs:** CLI 2.1.323, `srt` 0.0.83. n 40 per cell per arm; 480 of 480 runs usable, 0 retried. The seeds are now fitted.
- **Builds:** 6.2.1 (main 82fc0aa) and quiet at a503ac4 (`makoto2.py` sha256 93a29fbd…). In the data the quiet arm is named `collect`.

## Verdict
**The ship rule fails on one condition, so quiet is not merged and main stays 6.2.1.** The cell that failed last round now passes; a different one fails.

| cell | pass: plain; 6.2.1; quiet | cost ratio to plain: 6.2.1; quiet | holds per run: 6.2.1; quiet | notes per run: 6.2.1; quiet |
|---|---|---|---|---|
| Haiku, unrun | 20; 36; 33 | 1.33; 1.22 | 0.13; 0.10 | 1.08; 0.70 |
| Haiku, sigchange | 28; 39; 37 | 1.17; 1.35 | 0.83; 0.93 | 0.55; 0.95 |
| Sonnet, unrun | 21; 38; 38 | 1.38; 1.19 | 1.00; 0 | 0; 0.55 |
| Sonnet, sigchange | 27; 40; 40 | 1.58; 1.52 | 1.00; 1.00 | 0; 0.03 |

- **The rule, part by part:**
  - passes at least 6.2.1's minus 4: met in all four cells (−3, −2, 0, 0);
  - cost at most 6.2.1's plus 0.05: met in three cells, **failed in Haiku sigchange** (1.351 against a ceiling of 1.222);
  - cost below 6.2.1's somewhere: met in three cells.
- **Quiet against 6.2.1, cost ratio [95 %]:** Haiku unrun 0.92 [0.84, 1.00]; Haiku sigchange 1.15 [1.03, 1.32]; Sonnet unrun 0.86 [0.82, 0.90]; Sonnet sigchange 0.96 [0.92, 1.01].
- **Quiet against 6.2.1, passes:** no difference is significant (discordant 5 to 2, 2 to 0, 1 to 1, 0 to 0).
- **Against plain,** quiet gains +32.5, +22.5, +42.5 and +32.5 points; Holm rejects in all four cells.
- **Sonnet is fixed.** Its sigchange note is gone (0.03 per run) and its cost is at 6.2.1's; on unrun it has no hold and costs 1.19 against 1.38.

## Why Haiku sigchange costs more (post hoc, from the streams)
- **The probe reports a failing test in the middle of the change.** After the changed function's return type changes, the task's own test fails until the model updates it. The probe runs after each tool call and sends that failure: 38 failure notes in the 40 quiet runs, against 22 plain notes under 6.2.1.
- **It costs turns:** 19.2 per run against 16.2. The median cost is 0.0088 USD against 0.0076.
- **The assumption shown false:** that a failure read after a tool call is a failure of the finished change. Mid-change it is a read of a state the model has not finished.
- **Observed did not show it** because its plain note fired first and hid the difference (1.30 against 1.26).

## Predictions
| id | point (range) | measured | result |
|---|---|---|---|
| Q1 Haiku pass: unrun; sigchange | 34; 38 (28–40; 34–40) | 33; 37 | hit; hit |
| Q2 Haiku cost ratio: unrun; sigchange | 1.25; 1.27 (1.05–1.45; 1.05–1.55) | 1.22; 1.35 | hit; hit |
| Q3 Sonnet pass: unrun; sigchange | 39; 40 (33–40; 36–40) | 38; 40 | hit; hit |
| Q4 Sonnet cost ratio: unrun; sigchange | 1.33; 1.50 (1.1–1.5; 1.35–1.65) | 1.19; 1.52 | hit; hit |
| Q5 notes per run, Sonnet sigchange | 0 (0–0.2) | 0.03 | hit |
| Q6 holds per run, Sonnet: unrun; sigchange | 0.05; 1.0 (0–0.4; 0.8–1.0) | 0; 1.00 | hit; hit |
| Q7 the ship rule holds: 0.5 | | no | |

**No miss.**

## The four cells together (post hoc)
- Mean cost ratio to plain over the four cells: 6.2.1 1.37, quiet 1.32. Passes: 153 against 148 of 160.

## Candidates (the owner chooses)
1. **Merge quiet as it is.** The rule failed, so this is the owner's call: Sonnet is cheaper in both cells with no hold on unrun, and Haiku pays 0.18 more on sigchange.
2. **One more round:** a probe's failure is noted only when the same failure is read twice running, or only at the final answer. Either would drop the mid-change report; the second may bring back the hold on unrun.
3. **Stop here** and stay on 6.2.1.

## Spend
- Worker calls: kill tests 0.111 USD; live 11.062 USD (Haiku 1.328, Sonnet 9.734). Total **11.17 USD**, under the 25 USD cap.
