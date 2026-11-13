# Round "observed": a probe's pass counts only when the run showed something. Committed before any code or run; never edited after.

Owner, 2026-11-13: "Do 1 and 2". 1 is the revert of 6.3.0 to 6.2.1 (Makoto PR #187, merged 82fc0aa). 2 is this round.
- **Finding it starts from:** `research/collect/RESULTS.md`. A file that only defines functions exits 0 when run, with no output. Collect counted that as a check, and wrong callers went through.
- **Principle (the owner's Immediacy):** read the original instead of a derivation. An exit code with nothing printed is not a read of what the change does.

## The change (on collect, 42e5b5e)
- **One condition:** a probed program's pass stamps the files it reached only when the run exited 0, printed no error marker, **and printed something**.
- **A silent pass stamps nothing and says nothing.** Its files stay unchecked, so the note and the once-only hold of 6.2.1 cover them.
- **Nothing else changes.** No new state, setting or mechanism. The rule names no language, runner or task.
- **What it does not do:** a run by the model is judged as in 6.2.1; the condition applies to Makoto's own probes only.

## Checks before the live run
- **Tests** (with `srt`):
  - a probed program that prints and exits 0 checks the change silently;
  - a probed file that only defines functions leaves its change unchecked, and the final answer is held once, naming it;
  - a passing test file under pytest still checks what it reaches;
  - collect's other tests pass unchanged.
- **Kill test:** one call per model on sigchange. The stream must show the hold naming the dependent files.

## Live (CLI 2.1.323; `srt` 0.0.83)
- **Tasks:** 40 fresh tasks per cell, as in collect.

| model | family | seeds |
|---|---|---|
| Haiku | unrun level 3 | 9920000001 to 9920000040 |
| Haiku | sigchange, 12 users | 9930000001 to 9930000040 |
| Sonnet | unrun level 3 | 9940000001 to 9940000040 |
| Sonnet | sigchange, 12 users | 9950000001 to 9950000040 |

- **Arms:** plain, 6.2.1 (main 82fc0aa; `makoto2.py` sha256 d4a75b35…) and observed. In the data the observed arm is named `collect`, because the harness is `research/collect/harness/live_collect.py` unchanged.
- **Analysis:** `harness/analyze_observed.py`, collect's with this round's ship rule.
- **Spend cap:** 25 USD.
- **Fitted:** unrun and sigchange are fitted families; the result proves these families and no more.

## Ship rule
- **observed ships** when all of these hold:
  - in each of the four cells it passes at least 6.2.1's count minus 4;
  - in each of the four cells its cost ratio to plain is at most 6.2.1's plus 0.05;
  - in at least one cell its cost ratio to plain is below 6.2.1's.
- **Otherwise** it does not ship, and main stays 6.2.1.
- **A merge waits for the owner's word either way.**

## Predictions
| id | quantity | point | range |
|---|---|---|---|
| O1 | Haiku pass, observed: unrun; sigchange (of 40) | 34; 39 | 28 to 40; 35 to 40 |
| O2 | Haiku cost ratio, observed: unrun; sigchange | 1.25; 1.30 | 1.05 to 1.45; 1.05 to 1.6 |
| O3 | Sonnet pass, observed: unrun; sigchange | 38; 39 | 32 to 40; 35 to 40 |
| O4 | Sonnet cost ratio, observed: unrun; sigchange | 1.25; 1.55 | 1.05 to 1.5; 1.3 to 1.8 |
| O5 | holds per run, observed, sigchange: Haiku; Sonnet | 0.9; 1.0 | 0.5 to 1.0; 0.8 to 1.0 |
| O6 | holds per run, observed, unrun: Haiku; Sonnet | 0.1; 0.05 | 0 to 0.4; 0 to 0.4 |
| O7 | probability that the ship rule holds | 0.5 | |

- **What the predictions say:** on sigchange observed should behave as 6.2.1, hold and cost included; the gain stays on unrun, mostly on Sonnet.
