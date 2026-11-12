# Round "set and probe": results

**Measured.**
- **Sources:** `data/ANALYSIS_SP.json` (`harness/analyze_sp.py`, committed before the run), `data/live.ledger.jsonl.gz`.
- **Runs:** Haiku `claude-haiku-5-5`, CLI 2.1.322. n 40 per family per arm; 320 of 320 runs usable. The seeds are now fitted.
- **Builds:** mini is 6.1.0 (68c050f); set is 856a5cf; probe is ba6ae89.

## Verdict
**No variant meets the pre-registered ship rule, so the owner decides.**
- **Why they miss:** both miss the rule's cost condition, cost at most mini's. On sigchange, mini is cheap (1.03 times plain) because it does not help there.
- **The main finding:** on sigchange, set passes 38 of 40, against plain's 27 and 6.1.0's 20.

| unrun (n 40) | plain | mini (6.1.0) | set | probe |
|---|---|---|---|---|
| pass | 27 | 36 | 32 | 36 |
| against plain, points | | +22.5 [+5.0, +40.0]; p 0.035 | +12.5 [−5.0, +30.0]; p 0.30 | +22.5 [+7.5, +40.0]; p 0.023 |
| cost, ratio to plain | 1 | 1.22 [1.14, 1.32] | 1.24 [1.12, 1.37] | 1.21 [1.09, 1.33] |
| holds per run | 0 | 0.08 | 0.13 | 0.40 |

| sigchange (n 40) | plain | mini (6.1.0) | set | probe |
|---|---|---|---|---|
| pass | 27 | 20 | **38** | 30 |
| against plain, points | | −17.5 [−37.5, +5.0]; p 0.17 | **+27.5 [+10.0, +45.0]; p 0.0074; Holm rejects** | +7.5 [−7.5, +25.0]; p 0.55 |
| against mini, points | | | +45.0 [+30.0, +60.0]; discordant 0 to 18 | +25.0 [+5.0, +45.0]; p 0.041 |
| cost, ratio to plain | 1 | 1.03 [0.95, 1.13] | 1.26 [1.12, 1.42] | 1.34 [1.18, 1.53] |
| time, ratio to plain | 1 | 1.03 | 2.15 | 1.38 |
| holds per run | 0 | 0.45 | 0.40 | 1.30 |

- **Holm on unrun:** it rejects for no arm at n 40. The smallest p is 0.023, against a threshold of 0.0167.

## What it shows
- **The lookup works where width matters.** On a change with 12 users, set names the users and holds until runs reach them: 38/40, with no task that mini passed and set failed.
- **6.1.0 is not safe on wide changes.** On sigchange it passes 7 fewer tasks than plain (not significant). Its "same top-level folder" rule counts a run of one program as checking all of them.
- **set gives up some of unrun.** It passes 32 against mini's 36 (not significant; discordant 7 to 3). A changed file with no lookup edge is not demanded.
- **probe does not cut cost.** It matches mini on unrun at the same cost. On sigchange it is the costliest arm, holding 1.3 times per run. A failed probe still costs the turns to fix it, and passing probes saved little, because set's note already made the model run.

## Predictions
| id | point (range) | measured | result |
|---|---|---|---|
| P1 unrun pass: plain; mini; set; probe | 26; 35; 35; 36 | 27; 36; 32; 36 | hit ×4 |
| P2 sigchange pass | 20; 21; 27; 27 (12–28; 12–30; 16–36; 16–36) | 27; 20; 38; 30 | hit; hit; **MISS** (above); hit |
| P3 unrun cost: mini; set; probe | 1.28; 1.28; 1.10 | 1.22; 1.24; 1.21 | hit ×3 |
| P4 sigchange cost | 1.3; 1.4; 1.2 | 1.03; 1.26; 1.34 | hit ×3 |
| P5 probe, unrun final answers admitted with no message | 0.75 (0.5–0.95) | 28/40 = 0.70 | hit |
| P6 a variant ships: 0.45 | | none by the rule | the more likely side |
| P7 lines: set; probe | 260 (180–380); 330 (240–460) | 379; 473 | hit; **MISS** (above) |

## Spend
- Worker calls: kill tests 0.025 USD, live 1.736 USD. Total **1.761 USD**.

## Next (the owner chooses)
1. **Ship set, with one fix:** a changed runnable file with no lookup edge is demanded too, which is the likely cause of unrun's 32. Then confirm on fresh tasks.
2. **Build "one map"** (owner, 2026-11-12): all state on the map, with reads and writes links for literal paths. Measure it against set.
3. **Drop the probe as built:** it adds 94 lines and no gain.
