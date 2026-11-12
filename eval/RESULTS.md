> Historical record. This describes Makoto before 6.0.0, when it also enforced rules a, b, c and e; those rules, and the
> scripts, rule files and plan named below (`label.py`, `plant.py`, `variants.py`, `RULES*.md`, `plan/` and the rest), were removed in
> 6.0.0 and are in git history at `fe2e32c`. Nothing here describes what the code does now.

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

# Second round (rules in `RULES2.md`, committed in `322cb98` before the sample or any plant)
Before = `852bde0`, after = this head. Same corpus (342 sessions), same seed, same plants.

## 1. The five false positives, one cluster: how rule b treats punctuation next to a name
| hold | name | cause |
|---|---|---|
| d32499a1 #13, 22784a89 #23 | `.quantize` | a `.method(` call named in the prompt was read as a hidden file named in the prompt ("naming a file does not read it") |
| d32499a1 #35, 22784a89 #25 | `rep_`, `invoices_count` / `claims_count` | the prompt ends the sentence with the name (`rep_.`); the boundary test counted the `.` as part of the name |
| cf29e150 #45 | `app.core.depth_value` | the session had already written that name in an earlier edit, and it was treated as unread |

Fixes (`plugin/makoto2.py`, 10 lines): `contains()` ignores a sentence-ending `.,;:!?` after a name; a `.name(` call is not
subject to the "file named in the prompt" rule; a dotted name the session already wrote (`ledger.own`) is produced, not unread.
Tests `tests/test_rule_b_names.py`: the four false-positive cases fail on `852bde0` and pass now; three controls (a dotted
name nobody wrote, `.get(` that nobody read, a name found nowhere) pass on both, so the check is not switched off.
Two broader versions of the fixes were tried first and rejected: they also admitted `refunds.summarize`, `.get`,
`.union` and a first use of `app.core.depth_value`, which both labelers call missing.

| | before | after |
|---|---|---|
| Holds | 2603 | 2599 (the four sentence/method cases) |
| Hold-level false positives (`label.py`) | 5 | **1** |
| Finding-level false positives (`label.py`) | 2808 of 13135 | 2777 of 13105 (31 removed, all `fp`; no true finding lost; 1 true finding added) |
| Errors | 0 | 0 |
| Plants caught (first round) | 18 of 69 | 18 of 69 |

The one remaining hold-level false positive (cf29e150 #45) is a replay artifact. It is the same edit as #39, which both
labelers call a true hold (the name appeared nowhere). The recorded session ran #39 anyway; a live hook would have
denied it, so the name would not have been produced and #45 would be held again for the same true reason. I did not
treat denied-but-recorded edits as produced, because that would be wrong in a live session.

## 2. Independent label (n = 60 holds, seed 20261106, `independent.py`)
| | before (population 2603) | after (population 2599) |
|---|---|---|
| Hold-level false positives | 0/60 = 0.0% (95% Wilson 0.0% to 6.0%) | 0/60 = 0.0% (95% Wilson 0.0% to 6.0%) |
| Findings that name something that was present | 47/241 = 19.5% (15.0% to 25.0%) | 52/265 = 19.6% (15.3% to 24.8%) |
| of which rule b | 45/96 = 47% | 47/82 = 57% |

No sampled hold was a false positive: every one had at least one finding whose reading was missing (mostly rule d, a
Stop after edits that were never run). But about one finding in five, and about half of rule b's, names a subject the
independent label finds present (for example `AppError`, `i.get`). The hold stands, but its message tells the model to
read something it already has. The fix did not change this: it comes from Makoto not counting text the session wrote
or text from the prompt as evidence for names, which the independent label does count.

## 3. Recall with plants that need a reading (n = 67)
Plant rule excludes steps that need no reading (a Write that creates a file).
| plant | caught / n before | caught / n after |
|---|---|---|
| Q1: Edit or overwrite of a file whose every earlier Read was removed | 0/66 = 0.0% (95% Wilson 0.0% to 5.5%) | 0/66 = 0.0% (0.0% to 5.5%) |
| Q2: Stop with its runs removed | n = 0 | n = 0 |
| Q3: step naming a token seen in exactly one response, that response removed | 1/1 (20.7% to 100%) | 1/1 |
| all | 1/67 = 1.5% (0.3% to 8.0%) | 1/67 |

Makoto does not hold an edit of a file the session never read: rule a is satisfied by any earlier reading, and rule
b looks at names, not at the file being changed. I checked a plant by hand (a Write to `app/core.py` with its Read
removed, other files read): admitted. This is a design gap, not a fixed bug, and I did not change it.
n is small because only 115 dependent steps are admitted, 67 of them qualify.

## Everything else, re-run on the fixed code
Per-change table unchanged (all six changes: 2599 holds, 0 errors, 18/69). Clearability: 342 of 342 held Stops admitted after
the named action. Corruption experiment: 0 error blocks in 3569 later events, 13 extra rule holds (12 before).

# Third round (rules in `RULES3.md`, committed in `4b4bcb0` before either change was measured)
R0 = `ff63637`, R1 = R0 + rule e (`c221643`), R2 = R1 + evidence change (head). Same 342 sessions (n = 2718 dependent steps), same
plants, sample seed 20261107 (60 holds per run). `eval/summarize.py` produces every figure.

| | R0 | R1 (rule e) | R2 (evidence) |
|---|---|---|---|
| Holds | 2599 | 2644 | 2644 |
| Hold rate over 2718 dependent steps | 95.6% (94.8% to 96.3%) | 97.3% (96.6% to 97.8%) | 97.3% (96.6% to 97.8%) |
| Hold-level false positives, `label.py` | 1/2599 (0.0% to 0.2%) | 1/2644 (0.0% to 0.2%) | 1/2644 (0.0% to 0.2%) |
| Hold-level false positives, independent sample | 0/60 (0.0% to 6.0%) | 0/60 (0.0% to 6.0%) | 0/60 (0.0% to 6.0%) |
| Recall P1 (first round) | 1/1 | 1/1 | 1/1 |
| Recall P3 (first round) | 17/68 = 25.0% (16.2% to 36.4%) | 68/68 = 100% (94.7% to 100%) | 68/68 |
| Recall Q1, edit of an unread file | 0/66 = 0.0% (0.0% to 5.5%) | 66/66 = 100% (94.5% to 100%) | 66/66 |
| Recall Q3 / Q2 | 1/1 / n=0 | 1/1 / n=0 | 1/1 / n=0 |
| Recall all Q | 1/67 = 1.5% (0.3% to 8.0%) | 67/67 = 100% (94.6% to 100%) | 67/67 |
| Misdirected findings, as committed | 58/262 = 22.1% (17.5% to 27.5%) | 65/283 = 23.0% (18.4% to 28.2%) | 42/260 = 16.2% (12.2% to 21.1%) |
| Misdirected findings, counting only calls that ran | 18/262 = 6.9% (4.4% to 10.6%) | 25/283 = 8.8% (6.1% to 12.7%) | **2/260 = 0.8% (0.2% to 2.8%)** |
| Errors | 0 | 0 | 0 |
| Held Stops cleared by the named action | 342/342 | 342/342 | 342/342 |
| Context bytes, 31-event suite | 1021 | 1021 | 1021 |
| Hold-message bytes over the corpus (mean per hold) | 3,975,351 (1529.6) | 4,105,569 (1552.8) | 3,866,614 (1462.4) |
| Warm / cold ms, suite (n = 31) | 1364 / 2214 (repeat 1417 / 2252) | 1401 / 2225 | 1425 / 2295 |

Per hook warm / cold ms (PreToolUse n=12, PostToolUse n=11, Stop n=8): R0 43.4 / 70.7, 43.4 / 71.8, 44.0 / 71.2 (repeat 45.4 / 71.9,
45.5 / 71.5, 46.0 / 72.6); R1 46.0 / 71.7, 44.3 / 71.7, 45.0 / 71.6; R2 45.0 / 72.7, 46.0 / 72.4, 47.1 / 76.4. The R0 repeat differs from the
first R0 by up to 2.5 ms, so the three versions are not distinguishable. Bytes in the suite are identical because it never edits an
existing file; over the corpus, rule e raises the bytes by 3.3% (45 more holds) and the evidence change lowers them to 2.7% below R0.

## Change 1: rule e, read before edit (R0 to R1)
Recall Q1 0/66 to 66/66 and P3 17/68 to 68/68. Hold rate 95.6% to 97.3%: **45 new holds** (42 Write overwrites, 3 Edits, none on a
Write that creates a file). Rule e has 318 findings in all holds; both labelers call all 318 true (no earlier Read, Write or Edit of the
file), and none of the 45 new holds is a false positive by either labeler. Tests `tests/test_read_before_edit.py`: 4 of 5 fail on `ff63637`
(the fifth, a file the session wrote itself needs no reading, is a control). The host's own Edit and Write tools also refuse a file
that was not read (as I understand them), so in an interactive session this rule mostly repeats that check; in these headless runs
42 overwrites of unread files went through.

## Change 2: evidence (R1 to R2)
Prompt text and the session's own writes and outputs count as evidence for a name, and a file name or directory inside a longer path
in the prompt or in a path the session wrote counts too. This replaces the rule that a path named in the prompt is not evidence.
Tests `tests/test_evidence.py`: 5 of 6 fail on `c221643` (the sixth, a name nobody wrote is still held, is a control); the three
round-two controls stay green. Target "52 of 265 to 0": as committed the share goes 65/283 to 42/260. Each remaining one is traced:
- 40 findings are present only through a call Makoto denied in this replay. The log recorded those calls as run, so the labeler counts
  their text; a live session would not have run them. Counting only calls that ran, the share is 25/283 (8.8%) to 2/260 (0.8%).
- 2 findings (2f9389e7 #7, rule a "Wrote" and rule b `docs/dev/errors.md`) share one cause: the Read of `errors.md` ran, but the replay
  also fed Makoto the Post of an Edit it had denied, which recorded a mutation and made that Read stale. Without that Post (live) the
  reading stays fresh. I did not change the replay.
No false positive was added: hold-level false positives are 1 by `label.py` (the round-two replay artifact) and 0/60 by the sample, in all three runs.

## Items (b) to (d), R2
Clearability 342/342. Corruption experiment (journal tampered mid-session, 3569 later events): 0 error blocks, 7 extra rule holds
(1846 against 1839 uncorrupted). The user's prompt is never blocked (tests).
