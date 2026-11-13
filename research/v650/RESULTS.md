# Round "v650": results

**Measured**, except where marked post hoc.
- **Sources:** `data/ANALYSIS_V650_haiku.json`, `…_sonnet.json`, `…_sonnet_nosrt.json` (`research/downstream/harness/analyze_downstream.py`, unchanged), `data/*/live.ledger.jsonl.gz`.
- **Runs:** CLI 2.1.323, `srt` 0.0.83. n 40 per cell per arm; 560 of 560 runs usable, 0 retried. The seeds are now fitted.
- **Builds:** 6.2.1 (`makoto2.py` sha256 d4a75b35…) and 6.5.0 as merged (main 34c9139, sha256 00e8ed91…). In the data the 6.5.0 arm is named `collect`.

## Verdict
**With the sandbox, the merged 6.5.0 repeats the downstream round in every cell. The rule fails on one of its ten conditions, without the sandbox: Sonnet sigchange costs 0.09 more than 6.2.1 against a bound of 0.05, although Makoto says the same thing in both arms in all 40 runs.**

| cell | pass: plain; 6.2.1; 6.5.0 | cost ratio to plain: 6.2.1; 6.5.0 | holds per run: 6.2.1; 6.5.0 | notes per run: 6.2.1; 6.5.0 |
|---|---|---|---|---|
| Sonnet, sigchange, sandbox | 38; 40; 40 | 1.48; 1.09 | 1.00; 0 | 0; 0.28 |
| Sonnet, unrun, sandbox | 13; 39; 40 | 1.59; 1.35 | 1.00; 0 | 0; 0.70 |
| Haiku, sigchange, sandbox | 23; 36; 39 | 1.20; 1.07 | 0.93; 0 | 0.63; 0.70 |
| Haiku, unrun, sandbox | 26; 34; 33 | 1.22; 1.20 | 0.10; 0.13 | 1.00; 0.83 |
| Sonnet, sigchange, no sandbox | 38; 40; 40 | 1.48; 1.58 | 1.00; 1.00 | 0; 0 |
| Sonnet, unrun, no sandbox | 13; 39; 39 | 1.59; 1.54 | 1.00; 1.00 | 0; 0 |

- **The rule, part by part** (gap = 6.5.0 minus 6.2.1):
  - Sonnet sigchange, sandbox: pass gap 0, cost gap −0.40 (bound −0.10): **met**;
  - Sonnet unrun, sandbox: pass gap +1, cost gap −0.24 (bound −0.05): **met**;
  - Haiku, sandbox: pass gaps −1 and +3, cost gaps −0.02 and −0.14 (bound +0.10): **met**;
  - Sonnet unrun, no sandbox: pass gap 0, cost gap −0.05 (bound +0.05): **met**;
  - Sonnet sigchange, no sandbox: pass gap 0 (met); cost gap +0.093 (bound +0.05): **failed**.
- **6.5.0 with sandbox against 6.2.1, cost ratio [95 %]:** Sonnet sigchange 0.73 [0.70, 0.77]; Sonnet unrun 0.85 [0.81, 0.90]; Haiku sigchange 0.89 [0.78, 1.00]; Haiku unrun 0.99 [0.90, 1.08].
- **Against plain, with sandbox:** Sonnet unrun +67.5 points (p below 0.0001) and Haiku sigchange +40.0 (p below 0.0001), Holm rejects both; Sonnet sigchange +5.0 (p 0.5; plain passed 38 of 40 this round) and Haiku unrun +17.5 (p 0.092), Holm rejects neither.

## The failed condition (post hoc)
- **Makoto's messages are the same.** In all 40 Sonnet sigchange runs without the sandbox, 6.5.0 sends what 6.2.1 sends: no note, one hold of the same form.
- **The cost differs in the model's own turns:** 6.60 turns per run against 6.35; mean cost 0.0554 USD against 0.0521; ratio 1.06 [1.02, 1.11].
- **Read:** two arms that say the same thing, differing by more than the bound. `RULES.md` named this risk for the rule. The same comparison gave +0.03 in `research/downstream` (with a note in 0.35 of runs) and −0.05 on unrun here.
- **No assumption of the design is shown false by it,** and no fix follows from it.

## With `research/downstream`
| cell, with sandbox | downstream (44f3540) | v650 (6.5.0) |
|---|---|---|
| Sonnet sigchange: pass; cost ratio | 40; 1.06 | 40; 1.09 |
| Sonnet unrun | 38; 1.31 | 40; 1.35 |
| Haiku sigchange | 38; 0.95 | 39; 1.07 |
| Haiku unrun | 35; 1.25 | 33; 1.20 |

- **Without the sandbox** the downstream build lost 5 passes and 0.11 on Sonnet unrun; 6.5.0, which sends no note there, loses 0 and costs 0.05 less than 6.2.1.

## Predictions
| id | point (range) | measured | result |
|---|---|---|---|
| V1 Sonnet sigchange, sandbox: pass; cost | 39; 1.10 (35–40; 1.0–1.3) | 40; 1.09 | hit; hit |
| V2 Sonnet unrun, sandbox: pass; cost | 38; 1.32 (33–40; 1.15–1.5) | 40; 1.35 | hit; hit |
| V3 Haiku, sandbox, pass: unrun; sigchange | 34; 37 (28–40; 31–40) | 33; 39 | hit; hit |
| V4 Haiku, sandbox, cost: unrun; sigchange | 1.25; 1.02 (1.05–1.45; 0.85–1.3) | 1.20; 1.07 | hit; hit |
| V5 Sonnet, no sandbox, pass: unrun; sigchange | 38; 40 (34–40; 36–40) | 39; 40 | hit; hit |
| V6 Sonnet, no sandbox, cost gap: unrun; sigchange | 0.00; 0.00 (±0.08 each) | −0.05; +0.09 | hit; **MISS** (above) |
| V7 notes per run, Sonnet, no sandbox | 0 (0–0.05) | 0 | hit |
| V8 the rule holds: 0.65 | | no | |

- **V6's miss** is the failed condition; see above.

## Also found
- **A hold that names pytest's cache file** (`.pytest_cache/v/cache/lastfailed`): 3 of 320 Haiku runs with Makoto in testwait and downstream, 0 of 400 Sonnet runs. Fixed in Makoto PR #190 (a folder holding `CACHEDIR.TAG` is left out of the map). This round ran without that fix.

## Limits
- Two fitted task families, two models, one CLI; n 40 per cell.

## Spend
- Worker calls: kill tests 0.182 USD, and 0.157 USD on a first kill test that was invalid (its runs shared a scratch folder; kept in `data/invalid_kill/`); live 14.133 USD (Haiku 1.263, Sonnet 9.068, Sonnet without sandbox 3.802). Total **14.47 USD**, under the 30 USD cap.
