# Makoto: start here

One file for a session that picks Makoto up. Read it top to bottom. Do not read the history to
rebuild it; what the history holds that matters is here or in the files it names.

Nothing outside this repository is read at launch. Only two steps need an outside input, and
each names its own: step 6 needs a live audit, and step 10 needs the shared mesh.

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

Done means three things hold together:

- `python3 tools/register_map.py` prints 77 RUNNER and 0 NOT-COUNTABLE.
- Every fired check passes worth.py on a fresh live record.
- The launch checklist passes.

The row designs are in `docs/FOUNDATION-14.md`.

## Steps

1. ~~Count register entries I1 to I3~~ (PR #100).
   check: `python3 tools/register_map.py` reads 0 UNCOVERED. plant: delete I3's row from
   `docs/REGISTER-MAP.tsv` and it exits 1. inputs: none open. owner: done.
2. ~~Make Stop instantaneous, measure worth, withhold unchanged repeats, make the verifier gate
   payable~~ (PR #101).
   check: `tests/test_hook_latency.py`, `tests/test_worth.py` and `tests/test_stop_unchanged.py`.
   plant: each file carries its own plant. inputs: none open. owner: done.
3. ~~Deterministic fixes for the false fires~~ (PR #102). The fixed cases are:
   - an informational runner call (`--version`, `--collect-only`) read as masking;
   - a searched or described trailer string read as authorship;
   - scratch cleanup read as destruction;
   - a compaction SubagentStop read as a claim;
   - a Bash read-only reader not counted as the probe;
   - a newly created branch read as an unknown ref;
   - a unit used in the file it landed in read as unclaimed.

   check: the per-check tests in each commit. plant: revert any one commit and its test reads
   red. inputs: none open. owner: done.
4. ~~Make the installed copy provably this checkout~~ (PR #102). The version moved to 3.3.0, and
   `docs/PLUGIN-DIGEST.tsv` pins its content.
   check: `tests/test_plugin_digest.py` and the launch checklist's installed-copy line.
   plant: change a byte under `plugin/` without a new pin row, and the test reads red.
   inputs: none open. owner: done.
5. ~~Give every blocking check an exit the session actually has~~ (PR #102).
   - A check blocks one session's stops at most `STOP_BLOCK_BOUND` (3) times.
   - gate.unprobed_fanout denies once per unprobed stretch, and the same dispatch retried goes
     through. A seat with no Read, Glob, Grep or Bash tool could never pay it.
   - gate.unwitnessed_verifier is paid by a red run of the same verifier in either order.

   Past the stop bound, the finding is printed and the stop goes through. No precaution can
   force endless churn: the session goes long, never forever. Other Pre denials stay unbounded,
   because each returns control and a bounded deny would let a destructive call through.
   check: `tests/test_stop_unchanged.py` (a session that never satisfies its check),
   `tests/test_dispatch.py::test_dispatch_unprobed_fanout_has_an_exit_for_a_session_with_no_reading_tool`,
   and `tests/test_obligation_gates.py::test_unwitnessed_verifier_is_silent_when_the_red_run_came_after`.
   plant: drop the spent filter in `dispatch._evaluate_and_gate`, and stop 4 blocks. Return the
   finding unconditionally in `lineage.unprobed_fanout_gate`, or drop `k not in red` in
   `switch.unwitnessed_verifier_gate`, and its test reads red.
   inputs: none open. owner: done.
6. Re-grade worth on a fresh live record, then subtract. Subtraction is the default: a check
   that still fails worth-it is removed, along with its register row reverting to NOT-COUNTABLE,
   rather than narrowed or joined by a new one.
   check: `python3 tools/worth.py AUDIT.jsonl VERDICTS.tsv` exits 0 over every fire since
   3.3.0 was installed. plant: a verdicts file missing one fire exits 2.
   inputs: the audit of a session run on 3.3.0 (`~/.makoto/audit.jsonl`), with a verdict for
   each fire. The 09-23 to 09-28 record reads 5 of 17 fired checks worth it, but it was measured
   before steps 2 to 5 and is not needed. owner: the next Makoto session.
7. Build the ratchet and the shared pieces: `kit.neighbours`, which is O(n·t) with one token
   blanked, and `kit.claim`.
   check: a test pins the NOT-COUNTABLE count at 14, and the count only falls. plant: flip any
   RUNNER row back and the test reads red. inputs: none open; the design is
   `docs/FOUNDATION-14.md`, "Shared pieces". owner: the next Makoto session.
8. Rows B36, H4, E9, D8, B14, F12, A14, B18, B37, F6, B28, A6, G3 and E8, cheapest first, one
   commit each. Each commit lowers the pin by 1.
   check: register_map moves the row to RUNNER; its catch test is red with the row removed;
   latency and worth stay green. plant: the catch case in the FOUNDATION-14 table for that row.
   inputs: each row's owes and paid-by are defined in the table. What each row still needs is
   its measured false rate on real sessions, and the corpus for that exists:
   `tools/corpus.py` over the transcripts in `~/.claude/projects/`. Two rows each
   have one open vocabulary question:
   - B14: the benefit-verb list.
   - D8: the narrowing-flag list.

   Both are settled by the corpus fires, not by judgement. owner: the next Makoto session.
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
