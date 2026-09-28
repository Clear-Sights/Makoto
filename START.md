# Makoto: start here

Nothing outside this repository is read at launch. Three steps need an outside input, and
each names its own: step 6 needs a live audit, step 10 the shared mesh, and step 12 two clones.
Prior art from Gabriel's other repositories is in `docs/PRIOR-ART.md`; each step cites the
item it uses.

## Launch checklist

Run `sh tools/launch_check.sh --suite` before anything else. Every line must read PASS. Each
FAIL prints the one act that clears it. If one cannot be cleared, stop and tell Gabriel which
line failed; do not work around it.

- The Python is 3.11 or newer, and pytest imports.
- The checkout is origin/main and the tree is clean.
- The three laws exit 0: `tools/render_checks.py --check`, `tools/register_map.py` and
  `tools/merge_pass.py`.
- Every installed Makoto copy is this checkout's `plugin/`, both version and content. Hooks load
  at session start, so a reinstall needs a new session.
- The session has the repositories it needs: ask to attach (add_repo) Clear-Sights/Scour and
  Clear-Sights/Measure-Zero, and clone both beside this repository, before anything else.
- DetIO is on: it loads as a plugin at the version DetIO main ships, with
  `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`. Check: the first turn's context carries the line "DetIO is
  installed in this session", and the launch line prints the installed version. Installed but
  disabled reads missing. If it is missing, stop and tell Gabriel.
- Scour, pinned at 45cd655 with the register at Measure-Zero c544c4e: `sh tools/scour.sh` exits 0
  and prints Scour's verdict line. Its findings are the work list, not a launch failure; a
  LAUNCH MISSING line is red and names the act that clears it. Run it again before calling any
  step done.
- The suite is green.

## Goal and path

Goal, his words (2026-09-28 00:23:33Z):
> Makoto is the perfect awareness layer, stopping missteps before they happen, at every layer,
> it's the blindspot sensor grid
> must cover perfectly and Deterministically whatever it covers
> without ever not being worth it, assuming of course even one thing triggers
> THEY should be effectively instantaneous

Every row is held to three bars, and a row lands only with all three green:

- **Deterministic.** No model is involved. Each trigger and each payment is a token or regex
  reading of one recorded event.
- **Instantaneous.** Both readings in `tests/test_hook_latency.py` stay green.
- **Worth it.** On its corpus replay, `tools/worth.py` reads catches at or above false fires
  plus repeats.

Makoto is done when all three hold:

- `python3 tools/register_map.py` prints RUNNER for every entry whose set a hook event can
  decide, each by one check whose predicate is the entry's effect; every NOT-COUNTABLE row names
  the fact no hook event carries (59 RUNNER and 18 NOT-COUNTABLE on 2026-09-28).
- Every fired check passes worth.py on a fresh live record.
- The launch checklist passes.

The row designs are in `docs/FOUNDATION-14.md`. The steps:

1. ~~Count register entries I1 to I3~~ (PR #100).
   check: `python3 tools/register_map.py` reads 0 UNCOVERED. plant: delete I3's row from
   `docs/REGISTER-MAP.tsv` and it exits 1. inputs: `docs/REGISTER.md` part 5. owner: done.
2. ~~Make Stop instantaneous, measure worth, withhold unchanged repeats, make the verifier gate
   payable~~ (PR #101).
   check: `tests/test_hook_latency.py`, `tests/test_worth.py` and `tests/test_stop_unchanged.py`.
   plant: each file carries its own plant. inputs: `tools/worth.py`. owner: done.
3. ~~Fix the 7 deterministic false-fire classes~~ (PR #102; the classes are in its commit titles).
   check: the per-check tests in each commit. plant: revert any one commit and its test reads
   red. inputs: each check's own test file. owner: done.
4. ~~Make the installed copy provably this checkout~~ (PR #102). The version moved to 3.3.0, and
   `docs/PLUGIN-DIGEST.tsv` pins its content.
   check: `tests/test_plugin_digest.py` and the launch checklist's installed-copy line.
   plant: change a byte under `plugin/` without a new pin row, and the test reads red.
   inputs: `docs/PLUGIN-DIGEST.tsv`. owner: done.
5. ~~Give every blocking check an exit the session actually has~~ (PR #102): the stop bound
   `STOP_BLOCK_BOUND` (3), a single fanout deny, verifier witness in either order, and the
   fail-open notice shown once per session.
   Past the stop bound, the finding is printed and the stop goes through. No precaution can
   force endless churn: the session goes long, never forever. Other Pre denials stay unbounded,
   because each returns control and a bounded deny would let a destructive call through.
   check: `tests/test_stop_unchanged.py` (a session that never satisfies its check),
   `tests/test_dispatch.py::test_dispatch_unprobed_fanout_has_an_exit_for_a_session_with_no_reading_tool`,
   and `tests/test_obligation_gates.py::test_unwitnessed_verifier_is_silent_when_the_red_run_came_after`.
   plant: drop the spent filter in `dispatch._evaluate_and_gate`, and stop 4 blocks. Return the
   finding unconditionally in `lineage.unprobed_fanout_gate`, or drop `k not in red` in
   `switch.unwitnessed_verifier_gate`, and its test reads red.
   inputs: `plugin/makoto/dispatch.py`. owner: done.
6. Re-grade worth on a fresh live record, then subtract (`docs/PRIOR-ART.md` item 4). Subtraction is the default: a check
   that still fails worth-it is removed, along with its register row reverting to NOT-COUNTABLE,
   rather than narrowed or joined by a new one.
   check: `python3 tools/worth.py AUDIT.jsonl VERDICTS.tsv` exits 0 over every fire
   recorded on 3.3.0. plant: a verdicts file missing one fire exits 2.
   inputs: the audit of a session run on 3.3.0 (`~/.makoto/audit.jsonl`), with a verdict for
   each fire. owner: the next Makoto session.
7. Build the ratchet and the shared pieces: `kit.neighbours`, which is O(n·t) with one token
   blanked, and `kit.claim`.
   check: a test pins the NOT-COUNTABLE count at 18, and the count only falls. plant: flip any
   RUNNER row back and the test reads red. inputs: the design is
   `docs/FOUNDATION-14.md`, "Shared pieces". owner: the next Makoto session.
8. (`docs/PRIOR-ART.md` item 3.) Rows B36, H4, E9, D8, B14, F12, A14, B18, B37, F6, B28, A6, G3 and E8, cheapest first, one
   commit each. Each commit lowers the pin by 1.
   check: register_map moves the row to RUNNER; its catch test is red with the row removed;
   latency and worth stay green. plant: the catch case in the FOUNDATION-14 table for that row.
   inputs: each row's owes and paid-by are defined in the table. What each row still needs is
   its measured false rate on real sessions, and the corpus for that exists:
   `tools/corpus.py` over the transcripts in `~/.claude/projects/`. B14's benefit verbs and D8's
   narrowing flags are settled by those corpus fires. Cheapest way: convert the corpus once and
   replay it once for all 14 rows and step 11's thresholds together, never once per row. Write the
   rows with the cheaper executor, each briefed with its catch test as ACCEPTANCE, and accept a row
   only on your own run of that test. owner: the next Makoto session.
9. Cut the per-call start cost of about 0.19 s for Pre plus Post.
   check: a latency reading of the Pre and Post shim time, with a bound. plant: a module-level
   compile added back reads red.
   inputs: which cut to make, lazy regex compiles or a resident process, is unmeasured. Measure
   the lazy-compile cut first, because it is the smaller change. owner: the next Makoto session.
10. Close the shared mesh (`MAKOTO/mesh`), which reads distance 7 after the harness fix.
   check: the mesh reads distance 0, with every triple giving catch red and pass green.
   plant: `MAKOTO/foundation/harness.orig.py` reads 19.
   inputs: the classifier refused a read of the remaining 7 reds and the 3 proposed I1 to I3
   cases as "Modify Shared Resources". The placement item in the handoff section carries the line
   that lifts it. owner: the next Makoto session.
11. Conduct rows J1 to J8, defined in `docs/CONDUCT.md` (`docs/PRIOR-ART.md` item 5): off-path acts, hand repeats, serial
    independent runs, duplicate shapes, unslotted units, re-reads, chunkable edits and small-call
    loops. Some of the conduct Gabriel requires is already live (the entries named in that file).
    These eight are not yet prevented.
    check: register_map carries each J row as RUNNER. plant: the catch case in its table row.
    inputs: the gap named on each row, which is a threshold to measure on `tools/corpus.py`, or an
    input that does not exist yet. The inputs that do not exist yet are the step-row reader (J1),
    the names index (J4), the mesh slot map (J5) and a recorded PreCompact event (J6).
    owner: the next Makoto session, after step 7's kit.neighbours.
12. One count and one owner per register entry (`docs/PRIOR-ART.md` items 1, 2 and 7). Derive the
    entry count from the register file by script, so no document types it. Join
    `docs/REGISTER-MAP.tsv` with Scour's declined() reasons into one table that names, per entry,
    the static probe (Scour), the dynamic runner (Makoto) or neither. Dedupe B7, B2, F2 and D1 by
    the MERGE-WITNESSES rule.
    check: a test that reads the count off the register file and fails on any typed count that
    disagrees. plant: type a wrong count into README.md and the test reads red.
    inputs: blobless clones (`git clone --filter=blob:none`) of `Clear-Sights/Scour` at 45cd655
    and `Clear-Sights/Measure-Zero` at c544c4e, the pins `tools/scour.sh` names. The join is a
    script, not a reading. Neither is needed before this step. owner: the next Makoto session.
13. Replace per-case recognizers with one mechanism per family (`docs/MECHANISM.md`). A case
    outside a list must never be ignored: record each command's effect as a Pre/Post tree digest
    rather than guessing it from names; read a verifier's verdict from its exit code; route prose
    claims through one claim reader; identify tools by the shape of their input.
    check: the attacker's violating cases (a case a live row claims but misses) turn red, and the
    count of module-level lists under `plugin/makoto` falls. plant: one attacker case that the old
    per-case hook passes reads red under the mechanism.
    inputs: the attacker's cases; the digest's per-call cost, measured against the 2 s bound;
    tools/corpus.py for the false rate. owner: the next Makoto session, after steps 7 and 8.
