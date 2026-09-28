# Makoto: start here

Nothing outside this repository is read at launch. Three steps need an outside input, and
each names its own: step 6 needs a live audit, step 10 the shared mesh, and step 12 two clones.
Prior art from Gabriel's other repositories is in `docs/PRIOR-ART.md`; each step cites the
item it uses.

## Launch checklist

Run `sh tools/launch_check.sh` before anything else (about 7 s). Every line must read PASS. Each
FAIL prints the one act that clears it. If one cannot be cleared, stop and tell Gabriel which
line failed; do not work around it.

- The Python is 3.11 or newer, and pytest imports.
- The checkout is origin/main and the tree is clean.
- The three laws exit 0: `tools/render_checks.py --check`, `tools/register_map.py` and
  `tools/merge_pass.py`.
- NOTE, not a stop: the line names the installed Makoto copy whose hooks run this session (from
  the account-sync manifest and `enabledPlugins`, read by `tools/makoto_copies.py`) and every
  unused copy beside it. The live copy should be this checkout's `plugin/`. Reinstalling it, or
  removing an unused copy, is Gabriel's act (hooks load at session start, so it lands next
  session); the line prints NOTE with the act and the session goes on.
- The session has the repositories it needs: clone Clear-Sights/Scour and Clear-Sights/Measure-Zero
  read-only beside this repository (blobless), before anything else. No step writes to either, so
  ask to attach one (add_repo) only if its clone is refused. Scour has no handoff of its own: its
  one open item is step 14 here.
- DetIO is on: it loads as a plugin at the version DetIO main ships, with
  `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`. Check: the first turn's context carries the line "DetIO is
  installed in this session", and the launch line prints the installed version. Installed but
  disabled reads missing. If it is missing, stop and tell Gabriel.
- Scour, pinned at efd27e9 with the register at Measure-Zero c544c4e: `sh tools/scour.sh` exits 0
  and prints Scour's verdict line. Its findings are the work list, not a launch failure; a
  LAUNCH MISSING line is red and names the act that clears it. Run it again before calling any
  step done.
- The skills cheap-execution and adversarial-review are loaded: the line reads each one's
  SKILL.md under `~/.claude/skills`. Every step is run the cheap-execution way, and every "done"
  follows an adversarial-review round.
- Codex is not a launch item: no step here uses it. A step that does runs `sh tools/codex.sh`
  first; its LAUNCH MISSING line stops that step only and names the variable to set. Never commit
  `auth.json`.
- The suite is not a launch item: main's merge already ran it on five CI jobs. Before calling any
  step done, run `sh tools/launch_check.sh --suite` (about 76 s more) and see `suite green`.

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

The row designs are in `docs/FOUNDATION-14.md`.

Every open step starts with its projection: a mock of that step's wiring built only from pieces
that already exist, run with no model call, in minutes. It proves a loose version composes and
leaves each missing piece as a row in `docs/v9/VOIDS.tsv` (step, item, void, measured by). The
voids are then filled in file order, each under the step's cap. A step ends met, or at its cap
records `measured-not-met` with the reading in its VOIDS row and the session goes on to the next
step. Caps are defaults, not measurements: the first filled void replaces each with its measured
cost. The v9 tables the projections read are in `docs/v9/` (predicates, owners, words), copied
from the registry v9 work so no step reaches outside this repository for them.

The steps:

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
   projection: `python3 tools/project.py 6 AUDIT.jsonl VERDICTS.tsv` (no model). On the recorded
   `MAKOTO/foundation/audit-2026-09-28.jsonl` and `verdicts-2026-09-28.tsv` (shared project
   folder) it prints `PROJECT 6 checks=17 worth=5 not=12 fires=125` in 2 s. The 12 not-worth
   checks are step 6 rows in VOIDS. cap: 2 model calls and 5 minutes per VOIDS row; the step
   ends when every row is re-graded on a 3.4.6 record or subtracted.
   Stop: at the cap, record the measured number in VOIDS and go on.
7. Build the ratchet and the shared pieces: `kit.neighbours`, which is O(n·t) with one token
   blanked, and `kit.claim`.
   check: a test pins the NOT-COUNTABLE count at 18, and the count only falls. plant: flip any
   RUNNER row back and the test reads red. inputs: the design is
   `docs/FOUNDATION-14.md`, "Shared pieces". owner: the next Makoto session.
   projection: none needed. The ratchet is one test over `python3 tools/register_map.py`'s count,
   and kit.neighbours and kit.claim are specified in "Shared pieces". cap: 10 model calls and 30
   minutes for the step.
   Stop: at the cap, record the measured number in VOIDS and go on.
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
   projection: `python3 tools/project.py 8` (no model) parses each row's v9 line with the
   evaluator: `PROJECT 8 lines=14 parsed=2 refused=12`. The 12 refused are step 8 rows in VOIDS and
   wait on step 13's language; A6 and E8 go through the corpus replay now. cap: 8 model calls and
   15 minutes per row.
   Stop: at the cap, record the measured number in VOIDS and go on.
9. Cut the per-call start cost of about 0.19 s for Pre plus Post.
   check: a latency reading of the Pre and Post shim time, with a bound. plant: a module-level
   compile added back reads red.
   inputs: which cut to make, lazy regex compiles or a resident process, is unmeasured. Measure
   the lazy-compile cut first, because it is the smaller change. owner: the next Makoto session.
   projection: none needed; this is a measurement (`python3 -X importtime` on the Pre shim), not
   research. cap: 4 model calls and 10 minutes.
   Stop: at the cap, record the measured number in VOIDS and go on.
10. Close the shared mesh (`MAKOTO/mesh`), which reads distance 7 after the harness fix.
   check: the mesh reads distance 0, with every triple giving catch red and pass green.
   plant: `MAKOTO/foundation/harness.orig.py` reads 19.
   inputs: the classifier refused a read of the remaining 7 reds and the 3 proposed I1 to I3
   cases as "Modify Shared Resources". The placement item in the handoff section carries the line
   that lifts it. owner: the next Makoto session.
   projection: the mesh is already the projection: `MAKOTO/mesh/mesh.py` over `mesh.tsv` (181
   cases) with `harness.py`, and `placement.tsv` (63 rows) as the slot map, all in the shared
   project folder. First sub-step: copy `mesh.py`, `harness.py` and `mesh.tsv` into
   `tools/mesh/` and run it there (cap: 2 model calls and 5 minutes). Its one void, the 7 unread
   reds, is a step 10 row in VOIDS. cap: 4 model calls and 10 minutes.
   Stop: at the cap, record the measured number in VOIDS and go on.
11. Conduct rows J1 to J8, defined in `docs/CONDUCT.md` (`docs/PRIOR-ART.md` item 5): off-path acts, hand repeats, serial
    independent runs, duplicate shapes, unslotted units, re-reads, chunkable edits and small-call
    loops. Some of the conduct Gabriel requires is already live (the entries named in that file).
    These eight are not yet prevented.
    check: register_map carries each J row as RUNNER. plant: the catch case in its table row.
    inputs: the gap named on each row, which is a threshold to measure on `tools/corpus.py`, or an
    input that does not exist yet. The inputs that do not exist yet are the step-row reader (J1),
    the names index (J4), the mesh slot map (J5) and a recorded PreCompact event (J6).
    owner: the next Makoto session, after step 7's kit.neighbours.
    projection: first sub-step, write `docs/v9/conduct-lines.tsv` (one v9 line per J row, from
    `docs/CONDUCT.md`) and add `python3 tools/project.py 11` to parse it the way step 13 does
    (cap: 4 model calls and 10 minutes). J4's names index exists as Scour's names ledger
    (`sh tools/scour.sh` prints `names=`), and J5's slot map as `MAKOTO/mesh/placement.tsv`. J1 (no
    step-row reader) and J6 (no recorded PreCompact event) have nothing to project from; they are
    step 11 rows in VOIDS. cap: 4 model calls and 10 minutes per row.
    Stop: at the cap, record the measured number in VOIDS and go on.
12. One count and one owner per register entry (`docs/PRIOR-ART.md` items 1, 2 and 7). Derive the
    entry count from the register file by script, so no document types it. Join
    `docs/REGISTER-MAP.tsv` with Scour's declined() reasons into one table that names, per entry,
    the static probe (Scour), the dynamic runner (Makoto) or neither. Dedupe B7, B2, F2 and D1 by
    the MERGE-WITNESSES rule.
    check: a test that reads the count off the register file and fails on any typed count that
    disagrees. plant: type a wrong count into README.md and the test reads red.
    inputs: blobless clones (`git clone --filter=blob:none`) of `Clear-Sights/Scour` at efd27e9
    and `Clear-Sights/Measure-Zero` at c544c4e, the pins `tools/scour.sh` names. The join is a
    script, not a reading. Neither is needed before this step. owner: the next Makoto session.
    projection: `python3 tools/project.py 12` (no model) joins `docs/v9/owners.tsv` with
    `docs/REGISTER-MAP.tsv`: `PROJECT 12 entries=77 both=25 makoto=38 none=12 scour=2 map_only=0
    owners_only=0`. No void. cap: 6 model calls and 15 minutes for the count test.
    Stop: at the cap, record the measured number in VOIDS and go on.
13. One evaluator of the register's predicate lines, script only, at Pre in milliseconds (his
    rulings 2026-09-28 02:56Z and 03:27Z: no after-the-fact reading, no model). Start from branch
    `claude/register-evaluator` (504f2c5: `substrate/line.py` parses and evaluates the v9 language,
    38 tests, every v9 line parses). Add a read ledger (path to content hash when the session read
    it) so lineage and drift are lines; a claim reader as a word table plus regexes; one config file
    of named sets; then ONE check that runs every line and retires each entry's old check as its
    line lands. An entry with no line is not claimed and names its missing fact.
    check: every round-nine escape (the attack's per-entry cases) is a plant in `tests/` that reads
    red on main and green here, and each claimed entry has exactly one line. plant: delete one line
    and its entry's plant reads red.
    inputs: the v9 lines in `docs/v9/predicates.tsv`, and the attack's case list, copied into the
    repository when the step starts. owner: the next Makoto session.
    projection: `python3 tools/project.py 13` (no model; it reads the evaluator out of git at
    504f2c5) prints `PROJECT 13 lines=77 parsed=48 refused=29` in under 1 s. The 29 refused are
    step 13 rows in VOIDS, each naming the construct the language lacks (`refs(...)`, set
    difference, `exists n`, `contains`, `decorated`); fill them in VOIDS order. cap: 6 model calls
    and 10 minutes per row.
    Stop: at the cap, record the measured number in VOIDS and go on.
14. Scour's judge (moved from Scour's handoff, row SR1): make Scour's reader catch what
    adversarial-review catches, so adversarial-review can leave the launch rows. Replay both rounds
    in Scour's `tests/fixtures/attack/findings.tsv` (check out each head, pass its base) with
    `python3 -m scour.gate.judgment --on --diff BASE --model MODEL --store /tmp/verdicts.json
    --ledger /tmp/scour-self.txt`, with `SCOUR_JUDGMENT_TOKENS` set, in the Scour clone at
    2bface1fd0855b9c228be3ffb5d8cbaeb2044c5d (Scour #31; the reader it needs landed in #30). It
    writes only under `/tmp`, never to Scour's tree. First sub-step: move `SCOUR_PIN` in
    `tools/scour.sh` from efd27e9 to 2bface1 and see `sh tools/scour.sh` exit 0 with its verdict
    line (cap: 2 model calls and 5 minutes); until then launch stays at efd27e9, the pin last run.
    Measured 2026-09-28, curated (one unit, its seams, its ledger rows, one question per call,
    memory and thinking off, about 930 tokens fixed per call): Haiku 4.5 1/6 at 82k+144k tokens
    (37+72 calls); Sonnet 5 0/6 at 109k+193k; Opus 5.5 2/6 asked only the 8 unit-questions the
    findings sit on, 277k (153k output with thinking off); uncurated Opus 0/6 at 35k+51k. Warm on an
    unchanged tree: 0 calls; one planted change: 1 call, 1.6k. Misses: H9, M12 and S1 fully or in
    part; M13 needs a run, so no tool-less reader can catch it. Open this step only when a new model
    or a new fault class is in hand.
    check: 6 of 6 in `findings.tsv` named, scored by hand against its id column. plant: a finding
    removed from the reader's input reads as a miss.
    inputs: a blobless clone of `Clear-Sights/Scour` at 2bface1 (its
    `tests/fixtures/attack/findings.tsv`, the two attack rounds with their base and head commits,
    and `scour/gate/judgment.py`), and a model name for `--model`. owner: the next Makoto session.
    projection: `python3 -m pytest -q tests/test_layers.py -k Judgment` in the Scour clone (no
    model): the reader command (READER in `scour/gate/judgment.py`) set to a script replays hot,
    warm and changed at 0 tokens, and a unit judged twice reads red. cap: 120 model calls (both
    rounds, one model: 109 unit-questions plus the 8 gold-unit reruns) and 45 minutes. Done when
    one model names all 6: write that model here and drop adversarial-review from every launch
    row; otherwise record the model tried, its catch count and its tokens in VOIDS, and
    adversarial-review stays.
    Stop: at the cap, record the measured number in VOIDS and go on.
