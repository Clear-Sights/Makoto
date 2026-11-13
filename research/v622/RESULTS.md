# Round "6.2.2": results

**Measured.**
- **Sources:** `data/ANALYSIS_V622_haiku.json`, `data/ANALYSIS_V622_sonnet.json` (`harness/analyze_v622.py`, committed before the runs), `data/*/live.ledger.jsonl.gz`.
- **Runs:** CLI 2.1.323. n 40 per cell per arm; 480 of 480 runs usable. The seeds are now fitted.
- **Build:** Makoto PR #184 at 561c858.

## Verdict
**The ship rule fails in all four cells, so 6.2.2 is not merged.** The note now reaches Sonnet, and Sonnet still does not run its code until it is held.

| cell | pass: plain; 6.2.1; 6.2.2 | cost ratio: 6.2.1; 6.2.2 | holds per run: 6.2.1; 6.2.2 | notes per run: 6.2.1; 6.2.2 |
|---|---|---|---|---|
| Haiku, unrun | 25; 33; 37 | 1.27; 1.32 | 0.15; 0.10 | 1.15; 1.10 |
| Haiku, sigchange | 25; 40; 40 | 1.24; 1.39 | 0.83; 0.90 | 0.58; 1.08 |
| Sonnet, unrun | 16; 40; 35 | 1.49; 1.48 | 1.00; 0.80 | 0; 1.00 |
| Sonnet, sigchange | 37; 40; 40 | 1.53; 1.63 | 1.00; 1.00 | 0; 1.00 |

- **Where the rule fails:**
  - cost above 6.2.1's plus 0.05 in three cells: Haiku unrun by 0.054, Haiku sigchange by 0.15, Sonnet sigchange by 0.10;
  - pass below 6.2.1's minus 4 in the fourth: Sonnet unrun, 35 against 40.
- **The diagnosis was right and the fix did not help.**
  - Under Sonnet the note now fires once per run, where it fired 0 times.
  - Holds stay at 0.8 to 1.0 per run. Told to run the program, Sonnet still answers first, and runs only when held.
- **Haiku sigchange took longer under 6.2.2:** 87 s against 6.2.1's 39 s. In two runs the model wrote long checking scripts of its own; each ran for over 8 minutes.
- **Both Makoto arms beat plain** in three cells (p at most 0.039). In Sonnet sigchange plain already passes 37 of 40.

## Predictions
| id | point (range) | measured | result |
|---|---|---|---|
| W1 Sonnet unrun pass: plain; 6.2.1; 6.2.2 | 16; 37; 37 (8–26; 30–40; 30–40) | 16; 40; 35 | hit ×3 |
| W2 Sonnet sigchange pass | 28; 39; 39 (20–36; 33–40; 33–40) | 37; 40; 40 | **MISS** (above); hit; hit |
| W3 Sonnet holds per run: 6.2.1; 6.2.2 | 1.0 (0.9–1.1); 0.3 (0.05–0.8) | 1.00; 0.90 | hit; **MISS** (above) |
| W4 Sonnet cost, 6.2.2: unrun; sigchange | 1.40; 1.35 (1.15–1.7; 1.1–1.65) | 1.48; 1.63 | hit; hit |
| W5 Haiku pass, 6.2.2: unrun; sigchange | 35; 36 | 37; 40 | hit; hit |
| W6 Haiku cost, 6.2.2: unrun; sigchange | 1.33; 1.33 (1.1–1.55; 1.1–1.6) | 1.32; 1.39 | hit; hit |
| W7 the ship rule holds: 0.6 | | no | the less likely side |

**W3 is the round's finding.** The miss traces to an assumption the data shows false: that Sonnet would act on a note.

## What it means
- **A note does not move Sonnet.** Only the hold does, so on Sonnet every run pays for a thrown-away answer.
- **That strengthens `research/ideal/IDEAL.md`.** The run should not be the model's step at all.

## Spend
- Worker calls: kill tests 0.106 USD, live 11.481 USD (Haiku 1.327, Sonnet 10.154). Total **11.59 USD**.
