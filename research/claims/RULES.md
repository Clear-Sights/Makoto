# Round "claims": measure what the README claims and nothing has measured. Committed before any code or run; never edited after.

Owner, 2026-11-13: "now do 3 and 4".
- **3:** test what the README claims but nothing has measured: any language, and data links.
- **4:** run on a stronger model.

Makoto under test: 6.2.1, main 9ee9979 (`makoto2.py` sha256 d4a75b35…). Arms: plain and makoto. CLI 2.1.323.

## Part A: another language (Haiku)
- **Family `unrun_js`**, new: `gen/gen_unrun_js.py`.
- **The task:** a small Node.js project, CommonJS, no dependencies. The goal asks for a small edit whose natural first form fails only when run.
  - On even seeds, a new function in one module must call a module that already requires the first. The natural top-level `require` closes a cycle, and the partial export is `undefined` at call time.
  - On odd seeds, a new helper module is used through a wrong natural form (a named import of a default export) that throws at run.
- **Goal and grader:** the goal says "No need to run it; CI runs the tests." `grade.py` runs `node show.js` and checks the output.
- **Self-test:** the reference passes; the natural form and the untouched tree fail.

## Part B: a data chain (Haiku)
- **Family `datachain`**, new: `gen/gen_datachain.py`.
- **The task:** a Python project where `build.py` writes a JSON file that `report.py` reads. The goal asks for a change to what `build.py` writes: a renamed field, or a changed unit. That change breaks `report.py` unless it is updated too.
- **What the goal names:** only `build.py`'s behaviour. `grade.py` runs `build.py`, then `report.py`, and checks the report.
- **Self-test:** the reference passes; a change to `build.py` alone fails.

## Part C: a stronger model
- Sonnet `claude-sonnet-5-5` on the two families already used: unrun level 3 and sigchange with 12 users.

## Runs
- **Pilot, parts A and B only:** plain on 10 seeds per family (9720000001 to 10 and 9730000001 to 10), to see the baseline. It is reported and changes nothing.
- **Live:** 40 fresh tasks per family, plain and makoto.

| part | family | model | seeds |
|---|---|---|---|
| A | unrun_js | Haiku | 9720000101 to 9720000140 |
| B | datachain | Haiku | 9730000101 to 9730000140 |
| C | unrun | Sonnet | 9740000001 to 9740000040 |
| C | sigchange | Sonnet | 9750000001 to 9750000040 |

- **Kill test:** one makoto call per part.
- **Spend cap:** 40 USD for the worker calls.
- **Analysis, per family:** exact McNemar; task bootstrap (10,000 resamples, seed 44) for the pass difference and the cost ratio. For makoto runs, the hook's behaviour is read from the stream.

## What each result changes
- **A claim is supported** when makoto passes more than plain with p below 0.05. It is also supported when plain passes over 90 % and makoto loses no more than 2 tasks.
- **A claim is not supported** when makoto passes fewer than plain minus 4, or when the hook never held or noted in a family where plain fails for want of a run. The README then states the limit in place of the claim.
- **Part C:** the README states the measured gain and cost on Sonnet, whatever they are.
- **No code change ships from this round.** README changes go through a pull request.

## Predictions
| id | quantity | point | range |
|---|---|---|---|
| A1 | unrun_js pass (of 40): plain; makoto | 24; 33 | 12 to 36; 22 to 40 |
| A2 | unrun_js cost ratio | 1.35 | 1.1 to 1.7 |
| B1 | datachain pass: plain; makoto | 26; 33 | 12 to 38; 20 to 40 |
| B2 | datachain: makoto runs where a note or hold names `report.py` or the JSON file | 30 | 15 to 40 |
| C1 | Sonnet unrun pass: plain; makoto | 36; 38 | 28 to 40; 32 to 40 |
| C2 | Sonnet sigchange pass: plain; makoto | 35; 37 | 26 to 40; 30 to 40 |
| C3 | Sonnet cost ratio: unrun; sigchange | 1.2; 1.2 | 1.0 to 1.5; 1.0 to 1.6 |
| S | worker spend | 12 USD | 4 to 35 |
