# Round "downstream": results

**Measured.**
- **Sources:** `data/ANALYSIS_DOWNSTREAM_haiku.json`, `…_sonnet.json`, `…_sonnet_nosrt.json` (`harness/analyze_downstream.py`, committed before the runs), `data/*/live.ledger.jsonl.gz`.
- **Runs:** CLI 2.1.323, `srt` 0.0.83. n 40 per cell per arm; 560 of 560 runs usable, 0 retried. The seeds are now fitted.
- **Builds:** 6.2.1 (`makoto2.py` sha256 d4a75b35…) and downstream at 44f3540 (sha256 35d5d5ec…). In the data the downstream arm is named `collect`; `data/sonnet_nosrt/` holds it without the sandbox.

## Verdict
**With the sandbox the cut is made: Sonnet sigchange costs 1.06 times plain against 6.2.1's 1.54, with 40 of 40 passing and no held answer. The ship rule still fails, on the arm without the sandbox,** where the new note costs more on unrun and passes fewer. So nothing is merged as it stands.

| cell | pass: plain; 6.2.1; downstream | cost ratio to plain: 6.2.1; downstream | holds per run: 6.2.1; downstream | notes per run: 6.2.1; downstream |
|---|---|---|---|---|
| Sonnet, sigchange, sandbox | 33; 40; 40 | 1.54; 1.06 | 1.00; 0 | 0; 0.20 |
| Sonnet, unrun, sandbox | 17; 40; 38 | 1.52; 1.31 | 1.00; 0 | 0; 0.75 |
| Haiku, sigchange, sandbox | 34; 39; 38 | 1.21; 0.95 | 1.00; 0 | 0.60; 0.70 |
| Haiku, unrun, sandbox | 27; 34; 35 | 1.29; 1.25 | 0.15; 0.08 | 1.00; 0.63 |
| Sonnet, sigchange, no sandbox | 33; 40; 40 | 1.54; 1.57 | 1.00; 1.00 | 0; 0.35 |
| Sonnet, unrun, no sandbox | 17; 40; 35 | 1.52; 1.63 | 1.00; 1.00 | 0; 0.98 |

- **The rule, part by part** (gap = downstream minus 6.2.1):
  - Sonnet sigchange, sandbox: pass gap 0 (bound −4), cost gap −0.48 (bound −0.10): **met**;
  - Sonnet unrun, sandbox: pass gap −2, cost gap −0.21 (bound −0.05): **met**;
  - Haiku, sandbox: pass gaps +1 and −1, cost gaps −0.04 and −0.26 (bound +0.10): **met**;
  - Sonnet sigchange, no sandbox: pass gap 0, cost gap +0.03 (bound +0.05): **met**;
  - Sonnet unrun, no sandbox: pass gap −5 (bound −4), cost gap +0.11 (bound +0.05): **failed on both**.
- **Downstream with sandbox against 6.2.1, cost ratio [95 %]:** Sonnet sigchange 0.69 [0.66, 0.71]; Sonnet unrun 0.86 [0.82, 0.91]; Haiku sigchange 0.79 [0.71, 0.88]; Haiku unrun 0.97 [0.88, 1.07].
- **Passes against 6.2.1, with sandbox:** no difference is significant (discordant 0 to 0, 2 to 0, 2 to 1, 4 to 5).
- **Against plain, with sandbox:** Sonnet +17.5 points on sigchange (p 0.016) and +52.5 on unrun (p below 0.0001), Holm rejects both; Haiku +10.0 (p 0.29) and +20.0 (p 0.077), Holm rejects neither. Plain passed more than usual on sigchange this round (33 and 34 of 40).
- **Sonnet sigchange with sandbox costs 1.06 [1.01, 1.10] times plain** and passes 7 tasks more.

## What happened
- **Sonnet acts on the note.** It is sent in 0.20 of sigchange runs, the ones where a dependent was left unchanged, and all 40 pass with no hold. The risk named in the rules did not occur.
- **Without the sandbox the note is extra.** The hold stays, as designed, so the note only adds: on unrun it is sent in nearly every run, cost rises by 0.11, and 5 tasks pass under 6.2.1 that fail here (discordant 5 to 0, p 0.063). Why the passes fall is not diagnosed.
- **Haiku sigchange:** the note after the first edit lists every dependent, the hold is gone, and the cost falls below plain's.

## Predictions
| id | point (range) | measured | result |
|---|---|---|---|
| D1 Sonnet sigchange: pass; cost | 37; 1.25 (30–40; 1.05–1.5) | 40; 1.06 | hit; hit (at the edge) |
| D2 Sonnet sigchange: holds; notes per run | 0.05; 0.6 (0–0.4; 0.3–1.2) | 0; 0.20 | hit; **MISS** (below) |
| D3 Sonnet unrun: pass; cost | 39; 1.38 (33–40; 1.2–1.55) | 38; 1.31 | hit; hit |
| D4 Haiku pass: unrun; sigchange | 34; 35 (28–40; 27–40) | 35; 38 | hit; hit |
| D5 Haiku cost: unrun; sigchange | 1.28; 1.20 (1.05–1.5; 1.0–1.45) | 1.25; 0.95 | hit; **MISS** (below) |
| D6 Sonnet no sandbox, sigchange: pass; cost | 40; 1.58 (36–40; 1.4–1.75) | 40; 1.57 | hit; hit |
| D7 Sonnet no sandbox, unrun: pass; cost | 38; 1.55 (33–40; 1.35–1.75) | 35; 1.63 | hit; hit |
| D8 the ship rule holds: 0.35 | | no | |

- **D2's miss:** the prediction assumed a note in most runs. The note is sent only when a dependent was left unchanged, and Sonnet leaves one in about a fifth of runs.
- **D5's miss:** the prediction kept some cost for the note. With the hold gone, Haiku's run is as cheap as plain's.

## Candidate (the owner chooses)
- **Send the downstream note only where the sandbox is installed.** With the sandbox that build is this round's measured arm, byte for byte in behaviour. Without it, it is 6.4.0, where the hold already names the same files. No behaviour would ship that was not measured, so it needs tests and no new run.

## Limits
- Two fitted task families, two models, one CLI; n 40 per cell. The rule was chosen from sigchange, where every plain failure is an unchanged dependent.
- With the sandbox, a silent wrong edit of a dependent the model did change is no longer held. No such failure occurred in this round's 40 Sonnet sigchange runs with the sandbox, nor among the 43 failures examined before the round.

## Spend
- Worker calls: kill tests 0.148 USD; live 14.358 USD (Haiku 1.301, Sonnet 9.116, Sonnet without sandbox 3.941). Total **14.51 USD**, under the 30 USD cap.
