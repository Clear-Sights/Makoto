# Round "downstream": name the dependents that were not changed, when the change is made, instead of holding the answer. Committed before any code or run; never edited after.

Owner, 2026-11-13: "Now cut the sonnet dependant files" (6.4.0 costs 1.55 times plain on Sonnet sigchange, all of it the held answer).

## Finding it starts from (measured, post hoc, on the fitted seeds of observed, quiet and testwait)
- **Sonnet without Makoto failed 43 sigchange runs in those three rounds. All 43 wrong modules are files that use the changed file and that the model never changed.** None is a file it changed wrongly.
- **The hold works by naming.** It lists every unchecked file, the missed one among them; the model then finds and fixes it (`research/testwait` streams). The run it asks for shows nothing: those files print nothing.
- **So the piece the model lacks is a fact Makoto's map already holds,** and it is delivered one thrown-away answer too late.
- **Principles (the owner's):** Openness, supply exactly as many facts as a step needs; Immediacy, read the original, and Makoto has itself read that a run of these files shows nothing.

## The change (on 6.4.0, main 16265d0)
- **The downstream note.** After any completed tool call, when a file uses a changed file (through the map's links, at any distance), was not itself changed, is not yet checked, and no earlier note named it, one note names every such file with the changed files it uses:
  `Not changed, but uses a changed file: <file> (<changed files>); … Check each against the change.`
  It needs no sandbox. A node gains one flag, set when a note names it.
- **A silent pass no longer leaves a demand.** When Makoto's probe of a program exits 0 with no output and no error marker, the files it reached are stamped as run. Makoto does not ask the model for a run it has itself seen show nothing; the downstream note carries what the hold carried.
- **Unchanged:** a probe that prints still checks; a failing probe is still reported (a test's at the final answer); the plain note still follows only the edit tools; without the sandbox the hold is 6.2.1's.
- **The rule names no language, runner or task.**

## Checks before the live run
- **Tests:**
  - a dependent that was not changed is named once, after the tool call that made the change, whatever the tool, with and without `srt`;
  - a dependent that was changed is not named;
  - with `srt`, a tree whose probes are silent gets the note and no hold; without `srt`, the note and 6.2.1's hold;
  - 6.4.0's other tests pass, except the one that states a silent pass is held.
- **Kill test:** one call per model on sigchange and on unrun.

## Live (CLI 2.1.323; `srt` 0.0.83)
| model | family | seeds |
|---|---|---|
| Haiku | unrun level 3 | 10070000001 to 10070000040 |
| Haiku | sigchange, 12 users | 10080000001 to 10080000040 |
| Sonnet | unrun level 3 | 10090000001 to 10090000040 |
| Sonnet | sigchange, 12 users | 10100000001 to 10100000040 |

- **Arms:** plain, 6.2.1 (`makoto2.py` sha256 d4a75b35…) and downstream with the sandbox. In the data the downstream arm is named `collect`; the harness is `research/observed/harness/live_collect.py`, unchanged.
- **Fourth arm, Sonnet only:** downstream without the sandbox (`MAKOTO_SRT` naming no file), same seeds, written to `data/sonnet_nosrt/`. It is analysed with the same script against the same plain and 6.2.1 runs.
- **Analysis:** `harness/analyze_downstream.py`: testwait's, printing each cell's pass gap and cost gap to 6.2.1.
- **Spend cap:** 30 USD.
- **Fitted:** both families are fitted, and this rule was chosen from sigchange. The result proves these families and no more.

## Ship rule
All of these, where a gap is downstream minus 6.2.1 (passes of 40; cost ratio to plain):
- **Sonnet sigchange, with sandbox:** pass gap at least −4; cost gap at most −0.10. This is the cut asked for.
- **Sonnet unrun, with sandbox:** pass gap at least −4; cost gap at most −0.05, so 6.4.0's gain there is kept.
- **Haiku, both cells, with sandbox:** pass gap at least −4; cost gap at most +0.10.
- **Sonnet, both cells, without sandbox:** pass gap at least −4; cost gap at most +0.05.
- **A merge waits for the owner's word.**

## Predictions
| id | quantity | point | range |
|---|---|---|---|
| D1 | Sonnet sigchange, downstream: pass; cost ratio | 37; 1.25 | 30 to 40; 1.05 to 1.5 |
| D2 | Sonnet sigchange, downstream: holds per run; notes per run | 0.05; 0.6 | 0 to 0.4; 0.3 to 1.2 |
| D3 | Sonnet unrun, downstream: pass; cost ratio | 39; 1.38 | 33 to 40; 1.2 to 1.55 |
| D4 | Haiku, downstream, pass: unrun; sigchange | 34; 35 | 28 to 40; 27 to 40 |
| D5 | Haiku, downstream, cost ratio: unrun; sigchange | 1.28; 1.20 | 1.05 to 1.5; 1.0 to 1.45 |
| D6 | Sonnet without sandbox, sigchange: pass; cost ratio | 40; 1.58 | 36 to 40; 1.4 to 1.75 |
| D7 | Sonnet without sandbox, unrun: pass; cost ratio | 38; 1.55 | 33 to 40; 1.35 to 1.75 |
| D8 | probability that the ship rule holds | 0.35 | |

- **The main risk:** Sonnet ignored 6.2.2's note, which told it to run something. This note states a fact about a file instead. If Sonnet ignores it too, D1's passes fall to plain's, about 25 to 30, and the rule fails on passes.
