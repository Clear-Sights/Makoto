# Corpus gate for the blocks PR (run 2026-11-06)

Scripts: `corpus.py` (logs -> hook events), `variants.py` (builds each variant), `run_corpus.py`, `plant.py`,
`report.py`, `compare.py`, `corruption.py`. Rules: `RULES.md` (committed in `0ee4e77`, before any log was opened).
Raw logs stay in Clear-Sights/Tiller-from-the-Ashes (branch `principles`, `9ee87a2`) and the container's own
Claude Code transcripts; nothing was unpacked to disk.

## The claim this was meant to check
The README has no "measured zero false positives" claim. In git history it says the opposite: "The requested
universal 100% and zero false positives is not claimed" (README before `266088c`). The only earlier measurement
is `tools/measure_rates.py` on the fixture sets of the old 5.x code, which is not in this repository. So this
corpus is the first measurement of the current code, and there is no earlier figure to hold it to.

## Corpus (n)
- 972 run logs read: 958 distinct `goal-N.jsonl` stream-json logs from Tiller jobs (small coding tasks with tools
  Read/Write/Edit/Bash; the one log I inspected for its model shows claude-haiku-5-5, the rest I did not check) and 14 Claude Code session transcripts from this container
  (13 are my own Haiku worker runs from the first task; this session's own transcript is excluded).
- 629 had no tool call and were dropped; 1 was this session's own transcript, excluded; **342 sessions kept** (13 local, 329 Tiller).
  327 of the 342 have the prompt recorded (from a sibling `feed.json`); 15 do not.
- Dependent steps: **2718** (1561 Write, 815 Edit, 342 Stop; 0 `git commit`/`git push`). 63 Bash calls in total.
- Converted by script. Events only (no `transcript_path`); a step Makoto denied still has its recorded result.
  The first conversion synthesized each tool result; I changed the converter to use the log's own structured
  `tool_use_result` and reran. Hold counts were identical (2603), so this did not change any figure below.

## Labels (rules fixed before the run)
Each finding gets `true` or `fp` from `label.py`, a plain-text oracle that does not call Makoto. A hold is a false
positive only when all of its findings are `fp` (the block is justified if any finding is true); I added that
hold-level definition after the first counts, and report both levels. The oracle is looser than Makoto's own rules
for rules a and b (plain substring; a reading of a file the session wrote counts), so `fp` is an upper bound on
real false positives for those findings, and a `true` can hide a real false positive that the oracle cannot see.

## Baseline (main `13ffca2`)
| | n |
|---|---|
| Hold steps (all blocked) | 2603 of 2718 dependent steps (95.8%); 115 admitted |
| Findings a / b / c / d | 1259 / 5910 / 16 / 5950 |
| Finding-level `fp` | a 104, b 2704, c 0, d 0 (2808 of 13135) |
| **Hold-level false positives** | **5** (0.19% of holds), all rule b on `.quantize`, `rep_`, `invoices_count`, `claims_count`, `app.core.depth_value`; none is a Stop |
| Errors (infrastructure) | 0 |
| Stop retries blocked | 342 of 684 (the cap admits the second retry) |

## Per change, same corpus (n = 342 sessions, 69 plants)
| run | holds | blocked | FP holds | errors | stop retries blocked | plants caught / n | plants blocked | errors on plants |
|---|---|---|---|---|---|---|---|---|
| base | 2603 | 2603 | 5 | 0 | 342 / 684 | 18 / 69 | 18 | 0 |
| no block_in scope (default config) | 2603 | 2603 | 5 | 0 | 342 / 684 | 18 / 69 | 18 | 0 |
| no stop cap | 2603 | 2603 | 5 | 0 | 684 / 684 | 18 / 69 | 18 | 0 |
| fail-closed | 2603 | 2603 | 5 | 0 | 342 / 684 | 18 / 69 | 18 | 0 |
| all three | 2603 | 2603 | 5 | 0 | 684 / 684 | 18 / 69 | 18 | 0 |
| clearing text + prompt + journal recovery (HEAD) | 2603 | 2603 | 5 | 0 | 684 / 684 | 18 / 69 | 18 | 0 |
| base, `MAKOTO_BLOCK_IN` set outside the sessions | 0 | **0** | 0 | 0 | 0 | 0 / 69 | **0** | 0 |
| no block_in scope, same setting | 2603 | 2603 | 5 | 0 | 0 | 18 / 69 | 18 | 0 |

Planted faults (`RULES.md`): P1 named subject n=1 (caught 1), P2 unrun change n=0, P3 no reading n=68 (caught 17).
These are few because Makoto admits only 115 dependent steps. P3 plants are the first admitted dependent step with
every earlier reading removed; many of those steps are a Write that creates a new file, which legitimately needs no
reading, so 17/68 is not a recall figure. P1 is the sharper plant but has n=1.

Gate (as written in `RULES.md`: false positives must not rise above baseline, catches must not fall):
- **No block_in scope**: identical to base by default. With the variable set, blocks go from 0 to 2603, plant
  catches from 0/69 to 18/69, and false-positive blocks from 0 to 5. Kept on the owner's ruling; users who had set it
  gain 5 false-positive blocks per 2603.
- **No stop cap**: no change in holds or false positives; repeated Stop blocks rise from 342/684 to 684/684. None of
  the 5 false positives is a Stop, so no false-positive Stop is repeated. Kept.
- **Fail-closed**: **0 errors** on 342 sessions and 69 plants, so the condition is met. Kept.
- The literal gate "false positives stay at 0" is not met by any run, including base: the baseline has 5.

## The three later requirements
- **Every finding names the one action that clears it.** Test per rule: `tests/test_immediacy.py::test_the_named_action_clears_the_hold[a-d]`.
  On the corpus (`run_corpus.py --clear`): after each of the 342 held Stops the named action was performed and the
  Stop resent; **342 of 342 were admitted, 0 uncleared**. The simulated actions are a Read, WebFetch or Bash run of
  the finding's subject; the real model's action may differ.
- **UserPromptSubmit is never blocked.** Tests: `test_user_prompt_submit_is_never_blocked` and
  `test_user_prompt_submit_after_a_corrupted_journal_is_admitted_and_recorded`. The corpus cannot exercise it: all
  327 prompts come first in their session, before any error occurs, and none was blocked in any run.
- **A corrupted journal no longer blocks every later step.** Experiment (`--corrupt-mid`: tamper with the journal
  after the middle event of each session, n = 342 sessions, 3569 later events):
  | | error blocks (all false positives) | sessions with an error block | rule holds after | uncorrupted rule holds | extra |
  |---|---|---|---|---|---|
  | previous code (fail-closed, no recovery) | 3569 | 342 | 0 | 1821 | n/a |
  | HEAD | 0 | 0 | 1833 | 1821 | +12 |
  The 12 extra holds are steps whose reading was lost with the journal; this replay has no transcript to restore
  it from, which a live hook has.

## What this does not show
- The sessions are small coding tasks with no web tools (and, as far as I checked, one model), so rule c fired 16 times and rule d never saw a
  Bash run beyond 63 calls; these numbers say little about interactive sessions or other models.
- 15 sessions lack their prompt, which can make a rule-b hold look true.
- Replaying a recorded session cannot show what the model would have done after a block.
