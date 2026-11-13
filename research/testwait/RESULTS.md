# Round "testwait": results

**Measured.**
- **Sources:** `data/ANALYSIS_TESTWAIT_haiku.json`, `data/ANALYSIS_TESTWAIT_sonnet.json` (`harness/analyze_testwait.py`, committed before the runs), `data/*/live.ledger.jsonl.gz`.
- **Runs:** CLI 2.1.323, `srt` 0.0.83. n 40 per cell per arm; 480 of 480 runs usable, 0 retried. The seeds are now fitted.
- **Builds:** 6.2.1 (main 82fc0aa) and testwait at a893b78 (`makoto2.py` sha256 4bf316a7…). In the data the testwait arm is named `collect`.

## Verdict
**The ship rule holds in every part, so testwait is merged as 6.4.0.** It also meets the stricter 0.05 cost ceiling in the Haiku cells, where the rule asked only 0.10.

| cell | pass: plain; 6.2.1; testwait | cost ratio to plain: 6.2.1; testwait | holds per run: 6.2.1; testwait | notes per run: 6.2.1; testwait |
|---|---|---|---|---|
| Haiku, unrun | 24; 34; 34 | 1.26; 1.26 | 0.18; 0.15 | 1.10; 1.03 |
| Haiku, sigchange | 26; 39; 38 | 1.43; 1.25 | 0.98; 0.83 | 0.70; 0.70 |
| Sonnet, unrun | 13; 39; 40 | 1.54; 1.35 | 1.00; 0 | 0; 0.70 |
| Sonnet, sigchange | 25; 40; 40 | 1.54; 1.55 | 1.00; 1.00 | 0; 0 |

- **The rule, part by part:**
  - Sonnet passes at least 6.2.1's minus 4: met (+1, 0);
  - Sonnet cost at most 6.2.1's plus 0.05: met (−0.19, +0.01);
  - Sonnet cost below 6.2.1's in a cell: met (unrun, 1.348 against 1.535);
  - Haiku passes at least 6.2.1's minus 4: met (0, −1);
  - Haiku cost at most 6.2.1's plus 0.10: met (0.00, −0.18).
- **Testwait against 6.2.1, cost ratio [95 %]:** Haiku unrun 1.00 [0.91, 1.09]; Haiku sigchange 0.88 [0.79, 0.97]; Sonnet unrun 0.88 [0.84, 0.92]; Sonnet sigchange 1.01 [0.97, 1.05].
- **Testwait against 6.2.1, passes:** no difference (discordant 3 to 3, 2 to 1, 0 to 1, 0 to 0).
- **Against plain,** testwait gains +25.0 (Haiku unrun, p 0.041, Holm does not reject), +30.0 (p 0.002), +67.5 (p below 0.0001) and +37.5 points (p 0.0001); Holm rejects in the last three.

## What the three fixes left
- **Where the sandboxed run helps:** Sonnet unrun. No held answer (0 against 1.00 per run), 40 of 40, at 1.35 against 1.54.
- **Where it changes nothing:** Sonnet sigchange, and Haiku unrun: the same passes, holds and cost as 6.2.1.
- **Haiku sigchange, 1.25 against 1.43:** read with care. 6.2.1's mean time there is 103 s against a usual 40 s, so a few long runs lift its cost; across the four rounds 6.2.1's ratio in this cell was 1.27, 1.26, 1.17 and 1.43.

## Predictions
| id | point (range) | measured | result |
|---|---|---|---|
| T1 Haiku pass: unrun; sigchange | 34; 38 (28–40; 34–40) | 34; 38 | hit; hit |
| T2 Haiku cost ratio: unrun; sigchange | 1.24; 1.25 (1.05–1.45; 1.05–1.5) | 1.26; 1.25 | hit; hit |
| T3 Sonnet pass: unrun; sigchange | 38; 40 (33–40; 36–40) | 40; 40 | hit; hit |
| T4 Sonnet cost ratio: unrun; sigchange | 1.22; 1.52 (1.05–1.45; 1.35–1.68) | 1.35; 1.55 | hit; hit |
| T5 notes per run, Haiku sigchange | 0.6 (0.3–1.0) | 0.70 | hit |
| T6 holds per run, Sonnet: unrun; sigchange | 0.05; 1.0 (0–0.4; 0.8–1.0) | 0; 1.00 | hit; hit |
| T7 the ship rule holds: 0.6 | | yes | |

**No miss.**

## Limits
- Two fitted task families, two models, one CLI; n 40 per cell. The test-waits rule was chosen from sigchange.
- Sonnet sigchange still costs 1.55 times plain, all of it the held answer. Nothing in these four rounds reduced it.

## Spend
- Worker calls: kill tests 0.150 USD; live 11.053 USD (Haiku 1.364, Sonnet 9.689). Total **11.20 USD**, under the 25 USD cap.
- The four rounds since 6.2.1 (collect, observed, quiet, testwait): 45.7 USD.
