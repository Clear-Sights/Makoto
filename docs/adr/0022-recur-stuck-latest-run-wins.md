# 0022: canon.recur judges each key's most recent run

## Relocated design history

From `canonTimeoutRecur.py`'s module docstring (`canon.recur` bullet):

```text
(a bugfix: the original judged the instant a bad run closed and never looked further ahead, so a
retry loop that failed twice, had an unrelated call intervene, then genuinely succeeded on a later
attempt still read as permanently stuck).
```

From `recur_stuck()`:

```text
BUGFIX (this ticket, live-observed): the original judged each run the instant it closed and
returned True immediately on the first bad one, permanently for the rest of the calls list —
so [ERR, ERR, <different call>, ERR, ERR, ..., <same key succeeds>] stayed stuck-True even
though the SAME call went on to genuinely resolve later, just not immediately back-to-back
with the failing run (a different, unrelated call sat in between, e.g. checking a PR's status
between retries against a flaky API). A key whose retries eventually succeed, however many
unrelated calls sit in between, is not a stuck loop by the time the turn ends — only a key
whose MOST RECENT run is itself still bad should fire. Every run is now judged as it closes,
per key, and the LAST judgment for each key wins; a fresh success (even a lone one, not
itself part of a run>=2) for a key overwrites an earlier bad verdict for that same key.
```
