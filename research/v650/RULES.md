# Round "v650": the merged 6.5.0 itself, live. Committed before any run; never edited after.

Owner, 2026-11-13: "Merge", then "Now run it live".
- **Why:** `research/downstream/RESULTS.md` measured build 44f3540, which sent the unchanged-users note with and without the sandbox. 6.5.0 (main 34c9139; `makoto2.py` sha256 00e8ed91…) sends it only with the sandbox. This round measures the merged build on both sides.
- **No code changes in this round.**

## Live (CLI 2.1.323; `srt` 0.0.83)
| model | family | seeds |
|---|---|---|
| Haiku | unrun level 3 | 10120000001 to 10120000040 |
| Haiku | sigchange, 12 users | 10130000001 to 10130000040 |
| Sonnet | unrun level 3 | 10140000001 to 10140000040 |
| Sonnet | sigchange, 12 users | 10150000001 to 10150000040 |

- **Arms:** plain, 6.2.1 (`makoto2.py` sha256 d4a75b35…) and 6.5.0 with the sandbox; on Sonnet also 6.5.0 without the sandbox (`MAKOTO_SRT` naming no file), written to `data/sonnet_nosrt/`. In the data the 6.5.0 arm is named `collect`.
- **Harness and analysis:** `research/observed/harness/live_collect.py` and `research/downstream/harness/analyze_downstream.py`, both unchanged.
- **Kill test:** one call per model per family with the sandbox, and one Sonnet call per family without it. Without it the stream must show no "Not changed, but uses" note.
- **Spend cap:** 30 USD.
- **Fitted:** both families are fitted; the result proves these families and no more.

## Rule (downstream's, unchanged; gap = 6.5.0 minus 6.2.1, passes of 40 and cost ratio to plain)
- **Sonnet sigchange, sandbox:** pass gap at least −4; cost gap at most −0.10.
- **Sonnet unrun, sandbox:** pass gap at least −4; cost gap at most −0.05.
- **Haiku, both cells, sandbox:** pass gap at least −4; cost gap at most +0.10.
- **Sonnet, both cells, no sandbox:** pass gap at least −4; cost gap at most +0.05.
- **If it holds,** 6.5.0 stands as measured. **If it fails,** the failing part is reported and the owner decides between a fix and a revert to 6.4.0.

## Predictions
| id | quantity | point | range |
|---|---|---|---|
| V1 | Sonnet sigchange, sandbox: pass; cost ratio | 39; 1.10 | 35 to 40; 1.0 to 1.3 |
| V2 | Sonnet unrun, sandbox: pass; cost ratio | 38; 1.32 | 33 to 40; 1.15 to 1.5 |
| V3 | Haiku, sandbox, pass: unrun; sigchange | 34; 37 | 28 to 40; 31 to 40 |
| V4 | Haiku, sandbox, cost ratio: unrun; sigchange | 1.25; 1.02 | 1.05 to 1.45; 0.85 to 1.3 |
| V5 | Sonnet, no sandbox: pass, unrun; sigchange | 38; 40 | 34 to 40; 36 to 40 |
| V6 | Sonnet, no sandbox: cost gap to 6.2.1, unrun; sigchange | 0.00; 0.00 | −0.08 to +0.08; −0.08 to +0.08 |
| V7 | notes per run, Sonnet, no sandbox, both cells | 0 | 0 to 0.05 |
| V8 | probability that the rule holds | 0.65 | |

- **Why V8 is no higher:** without the sandbox 6.5.0 should behave as 6.2.1, and two arms that behave alike can differ by more than 0.05 in cost at n 40.
