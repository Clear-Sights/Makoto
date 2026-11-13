# Round "observed": results

**Measured.**
- **Sources:** `data/ANALYSIS_OBSERVED_haiku.json`, `data/ANALYSIS_OBSERVED_sonnet.json` (`harness/analyze_observed.py`, committed before the runs), `data/*/live.ledger.jsonl.gz`.
- **Runs:** CLI 2.1.323, `srt` 0.0.83. n 40 per cell per arm; 480 of 480 runs usable, 0 retried. The seeds are now fitted.
- **Builds:** 6.2.1 (main 82fc0aa) and observed at 0e26d1a (`makoto2.py` sha256 3609d685…). In the data the observed arm is named `collect`.

## Verdict
**The ship rule fails on one of its nine conditions, so observed is not merged and main stays 6.2.1.** The fix did what it was for: observed passes as many tasks as 6.2.1 in every cell. It costs too much in one cell.

| cell | pass: plain; 6.2.1; observed | cost ratio to plain: 6.2.1; observed | holds per run: 6.2.1; observed | notes per run: 6.2.1; observed |
|---|---|---|---|---|
| Haiku, unrun | 33; 33; 34 | 1.26; 1.25 | 0.15; 0.13 | 1.08; 0.98 |
| Haiku, sigchange | 28; 38; 39 | 1.26; 1.30 | 0.80; 0.98 | 0.53; 1.25 |
| Sonnet, unrun | 13; 39; 40 | 1.54; 1.33 | 1.00; 0 | 0; 0.63 |
| Sonnet, sigchange | 25; 40; 40 | 1.49; 1.63 | 1.00; 1.00 | 0; 1.00 |

- **The rule, part by part:**
  - passes at least 6.2.1's minus 4: met in all four cells (+1, +1, +1, 0);
  - cost at most 6.2.1's plus 0.05: met in three cells, **failed in Sonnet sigchange** (1.629 against a ceiling of 1.537);
  - cost below 6.2.1's somewhere: met (Haiku unrun 1.250 against 1.263; Sonnet unrun 1.332 against 1.539).
- **Observed against 6.2.1, cost ratio [95 %]:** Haiku unrun 0.99 [0.93, 1.06]; Haiku sigchange 1.03 [0.92, 1.16]; Sonnet unrun 0.87 [0.82, 0.91]; Sonnet sigchange 1.10 [1.05, 1.14].
- **Against plain,** observed gains +2.5 points (Haiku unrun, p 1.0), +27.5 (Haiku sigchange, p 0.001), +67.5 (Sonnet unrun, p below 0.0001) and +37.5 (Sonnet sigchange, p 0.0001); Holm rejects in the last three.
- **Collect's loss is gone.** On sigchange observed passes 39 and 40 of 40, where collect passed 35 and 29.

## Why Sonnet sigchange costs more (from the table)
- **The note.** With the sandbox, the note follows any tool call, so Sonnet gets one per run here. Under 6.2.1 it gets none, because it changes files through the shell and 6.2.1's note follows only the edit tools.
- **The note buys nothing on Sonnet:** holds stay at 1.00 per run. This is `research/v622/RESULTS.md`'s finding again, and observed inherited it from collect.
- **Haiku sigchange, time:** mean 121 s against 41 s, from three runs of 649, 1,243 and 1,245 s; the median is 46 s against 41 s. `research/v622` saw the same kind of run.

## Predictions
| id | point (range) | measured | result |
|---|---|---|---|
| O1 Haiku pass: unrun; sigchange | 34; 39 (28–40; 35–40) | 34; 39 | hit; hit |
| O2 Haiku cost ratio: unrun; sigchange | 1.25; 1.30 (1.05–1.45; 1.05–1.6) | 1.25; 1.30 | hit; hit |
| O3 Sonnet pass: unrun; sigchange | 38; 39 (32–40; 35–40) | 40; 40 | hit; hit |
| O4 Sonnet cost ratio: unrun; sigchange | 1.25; 1.55 (1.05–1.5; 1.3–1.8) | 1.33; 1.63 | hit; hit |
| O5 holds per run, sigchange: Haiku; Sonnet | 0.9; 1.0 (0.5–1.0; 0.8–1.0) | 0.98; 1.00 | hit; hit |
| O6 holds per run, unrun: Haiku; Sonnet | 0.1; 0.05 (0–0.4; 0–0.4) | 0.13; 0 | hit; hit |
| O7 the ship rule holds: 0.5 | | no | |

**No miss.** Every step landed in its range; the rule failed on a cost the predictions put at 1.55 and the rule capped at 6.2.1's plus 0.05.

## Next candidate (the owner chooses)
- **Send the note after a shell change only when the probe has something to say** (a failure). When the probe was silent, keep 6.2.1's rule: the note follows only the edit tools. That removes the one note per run that Sonnet ignores on sigchange, and leaves the unrun gain as it is. It needs its own run.

## Spend
- Worker calls: kill tests 0.153 USD; live 11.209 USD (Haiku 1.362, Sonnet 9.847). Total **11.36 USD**, under the 25 USD cap.
