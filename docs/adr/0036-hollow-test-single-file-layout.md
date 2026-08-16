# 0036: hollowTest analyzer and Stop adapter combined into one file

## Relocated design history

From `makoto/checks/hollowTest.py`'s module docstring:

```text
SPEC-5 Task 4 (owner-revised layout): the analyzer engine (formerly `stopchecks/hollow_test.py`)
and its Stop-hook adapter (formerly `stopchecks/stopcheck_hollow_test.py`) are combined into ONE
flat file here — the migration ticket left single-vs-paired-file layout to the executing session's
call; a single file is chosen because the two halves are always read/changed together and a flat
`checks/` package favors one file per detector, matching every other migrated check.
```
