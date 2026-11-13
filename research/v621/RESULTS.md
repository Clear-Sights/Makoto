# Round "6.2.1": results

**Measured.**
- **Sources:** `data/ANALYSIS_V621.json` (`harness/analyze_v621.py`, committed before the run), `data/live/*.ledger.jsonl.gz`.
- **Runs:** Haiku `claude-haiku-5-5`, CLI 2.1.323 (AMEND_1). n 40 per family per arm; 240 of 240 runs usable. The seeds are now fitted.
- **Build:** Makoto PR #182 at 19d8e13 (`makoto2.py` 424 lines, 60 tests).

## Verdict
**The ship rule holds, so 6.2.1 ships.**

| pass (of 40) | plain | 6.2.0 | 6.2.1 |
|---|---|---|---|
| unrun | 24 | 32 | 36 |
| sigchange (12 users) | 27 | 34 | 37 |

| 6.2.1 | unrun | sigchange |
|---|---|---|
| against plain, points | +30.0 [+12.5, +47.5]; p 0.0042; Holm rejects | +25.0 [+10.0, +42.5]; p 0.013; Holm rejects |
| against 6.2.0, points | +10.0 [−2.5, +25.0]; p 0.29 | +7.5 [−7.5, +22.5]; p 0.51 |
| cost ratio to plain (6.2.0's) | 1.34 [1.24, 1.45] (1.32) | 1.33 [1.16, 1.51] (1.34) |
| notes per run (6.2.0's) | 1.13 (1.85) | 0.63 (8.65) |
| holds per run (6.2.0's) | 0.20 (0.18) | 0.83 (0.40) |
| mean seconds (6.2.0's) | 20.6 (20.2) | 41.4 (68.5) |

- **Ship rule, each condition:**
  - unrun: 36 against the required 32 − 4;
  - sigchange: 37 against the required 34 − 4;
  - cost: 1.34 and 1.33, within 6.2.0's 1.32 and 1.34 plus 0.05.
- **Notes fell as intended:** on sigchange, from 8.65 per run to 0.63.
- **Cost did not fall.** Holds rose there, from 0.40 to 0.83 per run, and only 7 of 40 final answers were admitted the first time. With fewer notes the model more often reaches its final answer before running the users, so the hold does the work the notes did.
- **Time on sigchange** fell from 68.5 s to 41.4 s.
- **The pass differences against 6.2.0** are not significant.

## Predictions
| id | point (range) | measured | result |
|---|---|---|---|
| V1 unrun pass: plain; 6.2.0; 6.2.1 | 25; 36; 36 (17–32; 29–40; 29–40) | 24; 32; 36 | hit ×3 |
| V2 sigchange pass | 25; 36; 37 (16–32; 28–40; 28–40) | 27; 34; 37 | hit ×3 |
| V3 notes per run on sigchange: 6.2.0; 6.2.1 | 8.5 (6–11); 2.0 (1–5) | 8.65; 0.63 | hit; **MISS** (below) |
| V4 cost, 6.2.1: unrun; sigchange | 1.33; 1.33 | 1.34; 1.33 | hit; hit |
| V5 the ship rule holds: 0.65 | | yes | the more likely side |

## Limits
- **Not checked from the streams:** whether the two diagnosed failure kinds (a passing pytest that reaches too little) still occur.
- **The redirect links** are exercised by tests only.
- **Scope:** two Python families and one model, n 40, on CLI 2.1.323.

## Spend
- Worker calls: kill tests 0.034 USD, live 1.324 USD. Total **1.358 USD**.
