# Round "one map": results

**Measured.**
- **Sources:** `data/ANALYSIS_OM.json` (`harness/analyze_om.py`, committed before the run), `data/live.ledger.jsonl.gz`.
- **Runs:** Haiku `claude-haiku-5-5`, CLI 2.1.322. n 40 per family per arm; 320 of 320 runs usable. The seeds are now fitted.
- **Build:** Makoto PR #181 at 8a5c7dc (`makoto2.py` 412 lines, 55 tests).

## Verdict
**The ship rule holds, so one map ships as Makoto 6.2.0.**

| pass (of 40) | plain | mini (6.1.0) | set | one map |
|---|---|---|---|---|
| unrun | 21 | 39 | 36 | 36 |
| sigchange (12 users) | 24 | 16 | 32 | **38** |

| one map against plain | unrun | sigchange |
|---|---|---|
| points | +37.5 [+17.5, +57.5]; p 0.0026; Holm rejects | +35.0 [+17.5, +52.5]; p 0.0005; Holm rejects |
| cost ratio | 1.36 [1.24, 1.50] | 1.32 [1.18, 1.47] |
| holds per run | 0.13 | 0.40 |

- **Ship rule, each condition:**
  - unrun: 36 against the required 39 − 4;
  - sigchange: 38 against the required 32 − 4, and above plain's 24;
  - cost: 1.36 and 1.32, within set's 1.35 and 1.31 plus 0.05.
- **Against mini on sigchange:** +55.0 points [+40.0, +70.0]; discordant 0 to 22.
- **6.1.0 on sigchange, again:** 16 against plain's 24 (−20.0 points [−40.0, 0.0], p 0.12). With the last round's 20 against 27, it has passed fewer wide-change tasks than plain twice.
- **On unrun:** one map and set both pass 36, against mini's 39 (not significant; discordant 4 to 1).

## Predictions
| id | point (range) | measured | result |
|---|---|---|---|
| Q1 unrun pass: plain; mini; set; one map | 27; 35; 33; 35 (18–33; 28–40; 26–40; 28–40) | 21; 39; 36; 36 | hit ×4 |
| Q2 sigchange pass | 25; 21; 36; 36 (15–32; 12–30; 28–40; 28–40) | 24; 16; 32; 38 | hit ×4 |
| Q3 one map cost: unrun; sigchange | 1.25; 1.28 (1.1–1.5; 1.1–1.6) | 1.36; 1.32 | hit; hit |
| Q4 lines | 340 (250–420) | 412 | hit |
| Q5 the ship rule holds: 0.6 | | yes | the more likely side |

## Limits
- **Cost:** 1.32 to 1.36 times plain, above the owner's earlier 1.25 cap. 6.1.0 was 1.35 on these unrun tasks.
- **Scope:** two Python task families and one model; n 40.
- **Data links:** the reads and produced-by links were exercised by tests only. Neither family has a data chain.

## Spend
- Worker calls: kill tests 0.012 USD, live 1.732 USD. Total **1.744 USD**.
