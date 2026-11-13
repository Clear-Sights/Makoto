# AMEND_3: the first live run used a build whose probe gave false failures; it is stopped, and all four cells are re-run on the fixed build. Committed before the re-run; never edited after.

Owner, 2026-11-13: "first ensure it does the new testing thing", then "Fix it and rerun".

## Finding (measured, first run, Haiku, build 01b4901; seeds 9820000001 to 40 and 9830000001 to 40, now fitted)
- **unrun: the probe worked.**
  - 16 of 40 collect runs went through with no note and no hold.
  - 24 passed with no run by the model after its last edit.
- **sigchange: every collect run got a false failure.** The 39 usable runs carried 78 messages, all `ModuleNotFoundError: No module named 'app'`.
  - The probe ran each module of a package as a bare script, and ran test files the same way.
  - The modules had not failed.
- **The run was stopped** with Haiku at 239 of 240 calls and Sonnet at 0. Its data is `data/run1_haiku/`, kept as superseded; `data/ANALYSIS_run1_haiku.json` is reported, and is not the round's result.

## Fix (Makoto PR #185 at 42e5b5e; `makoto2.py` sha256 055c695e…, 537 lines; 77 tests with srt)
- **Python programs:** a probed Python file has every folder above it, up to the tree's root, on `PYTHONPATH`.
- **Python test files:** they run under `pytest` when pytest is installed.
- **Also on the PR, from 396ea64:** without the sandbox, the note follows only the edit tools, as in 6.2.1.

## Re-run
- **Scope:** all four cells, on fresh seeds.

| model | family | seeds |
|---|---|---|
| Haiku | unrun | 9870000001 to 9870000040 |
| Haiku | sigchange | 9880000001 to 9880000040 |
| Sonnet | unrun | 9890000001 to 9890000040 |
| Sonnet | sigchange | 9900000001 to 9900000040 |

- **Arms:** plain, 6.2.1 and collect at 42e5b5e. The harness, analysis, AMEND_2's ship rule and the predictions are unchanged.
- **Kill test:** one collect call on sigchange per model. The stream must show no `ModuleNotFoundError` from a probe.
