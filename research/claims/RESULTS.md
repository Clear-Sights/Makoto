# Round "claims": results

**Measured.**
- **Sources:** `data/ANALYSIS_CLAIMS.json` (`harness/analyze_claims.py`, committed before the runs), `data/*/live/*.ledger.jsonl.gz`.
- **Runs:** CLI 2.1.323; Makoto 6.2.1 (main 9ee9979). n 40 per family per arm; 320 of 320 runs usable. The seeds are now fitted.

## Verdict
**Every claim tested is supported by the pre-registered rule. On the JavaScript family that is only "no harm": plain passes every task.**

| part | family, model | plain | makoto | difference, points | cost ratio | holds; notes per run |
|---|---|---|---|---|---|---|
| A | unrun_js, Haiku | 40/40 | 40/40 | 0.0 | 1.21 [1.14, 1.27] | 0.28; 1.50 |
| B | datachain, Haiku | 6/40 | 19/40 | +32.5 [+12.5, +52.5]; p 0.0072 | 1.44 [1.35, 1.53] | 0.95; 1.45 |
| C | unrun, Sonnet | 16/40 | 38/40 | +55.0 [+37.5, +72.5]; p < 0.0001 | 1.68 [1.54, 1.83] | 1.00; 0.00 |
| C | sigchange, Sonnet | 28/40 | 40/40 | +30.0 [+17.5, +45.0]; p 0.0005 | 1.57 [1.51, 1.63] | 1.00; 0.00 |

- **Part A, another language.** Makoto's note and hold fire on Node.js tasks and no task is lost. No gain can show, since plain Haiku passes 40 of 40, and the pilot was 10 of 10. The cost is 1.21 times plain's for nothing gained on this family.
- **Part B, data links.**
  - The reads and produced-by links work live: in 37 of 40 makoto runs a note or hold named `report.py` or the JSON file.
  - Makoto passes 19 against plain's 6.
  - 21 runs still fail; they were not examined.
- **Part C, a stronger model.**
  - Sonnet does not run its code either when the goal says there is no need: plain passes 16 of 40 unrun tasks and 28 of 40 sigchange tasks.
  - Makoto takes those to 38 and 40.
  - Every Sonnet run was held exactly once, and no note was given. Why no note fired under Sonnet was not examined.
  - With a hold in every run, the cost is 1.57 to 1.68 times plain's.

## Predictions
| id | point (range) | measured | result |
|---|---|---|---|
| A1 unrun_js pass: plain; makoto | 24; 33 (12–36; 22–40) | 40; 40 | **MISS** (above); hit |
| A2 unrun_js cost ratio | 1.35 (1.1–1.7) | 1.21 | hit |
| B1 datachain pass: plain; makoto | 26; 33 (12–38; 20–40) | 6; 19 | **MISS** (below); **MISS** (below) |
| B2 runs naming `report.py` or the JSON file | 30 (15–40) | 37 | hit |
| C1 Sonnet unrun pass: plain; makoto | 36; 38 (28–40; 32–40) | 16; 38 | **MISS** (below); hit |
| C2 Sonnet sigchange pass: plain; makoto | 35; 37 (26–40; 30–40) | 28; 40 | hit; hit |
| C3 Sonnet cost ratio: unrun; sigchange | 1.2; 1.2 (1.0–1.5; 1.0–1.6) | 1.68; 1.57 | **MISS** (above); hit |
| S worker spend | 12 USD (4–35) | 7.18 USD | hit |

**Misses outside their range: 5.** I expected Sonnet to run its code unasked, and it did not. I also expected the JavaScript trap to catch Haiku, and it did not.

## Limits
- **Fitted families:** each was built for this purpose, and the two new ones were not tuned.
- **One wording:** the unrun tasks say "No need to run it". No task without that sentence was run on Sonnet.
- **Scope:** n 40; Python and JavaScript only; Go, Rust, Ruby and shell are covered by unit tests alone.

## Spend
- Worker calls: pilot 0.048 USD, kill tests 0.251 USD, live 6.878 USD (Haiku 0.462, Sonnet 6.416). Total **7.18 USD**.
