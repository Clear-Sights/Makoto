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
  installed in this session", and the launch line reads the live copy (the one Claude Code loads,
  `tools/makoto_copies.py HOME detio`) against the version on DetIO main and checks the hooks
  variable. Installed but disabled reads missing. If it is missing or behind main, stop and tell
  Gabriel.
- Scour, pinned at efd27e9 with the register at Measure-Zero c544c4e: `sh tools/scour.sh` exits 0
  and prints Scour's verdict line. Its findings are the work list, not a launch failure; a
  LAUNCH MISSING line is red and names the act that clears it. Run it again before calling any
  step done.
- The skills cheap-execution and adversarial-review are loaded: the line reads each one's
  SKILL.md under `~/.claude/skills`. Every step is run the cheap-execution way, and every "done"
  follows an adversarial-review round.
- Codex is not a launch item: a step that uses it runs `sh tools/codex.sh` first; its LAUNCH
  MISSING line stops that step only and names the variable to set. Never commit `auth.json`.
- Model choice (Gabriel 2026-09-28): audit across the asymmetry. Claude's work is read by Codex
  (`gpt-6-astra`, `gpt-6-sol`, any Codex model; `tools/codex_reader.py` is Scour's judgment reader),
  and Codex's work by Claude; Opus need not review Opus. Where a Claude model has shown better
  results on a specific aspect with curated context, use it for that aspect alone. Curate the
  context, and treat Codex as the cheaper per capability, relative to Claude only. Pick the model
  and effort by what the task would benefit from: a governing artifact gets the highest model; a
  task that would not benefit from a higher one gets the lower one.
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
  the fact no hook event carries (the split is read off that tool; `tests/test_ratchet.py` pins
  the NOT-COUNTABLE count and lets it only fall).
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
   inputs: the 3.3.0 audit with a verdict for each fire, `docs/v9/records/audit-3.3.0-2026-09-28.jsonl`
   and `docs/v9/records/verdicts-3.3.0-2026-09-28.tsv`; a fresh live record is the running
   session's `~/.claude/makoto_state/audit.jsonl`. The 2026-09-29 session's record (137 events
   under 3.4.8 to 3.4.16, ungraded) is `docs/v9/records/audit-3.4.8-to-3.4.16-2026-09-29.jsonl`;
   it needs a verdicts file before `tools/worth.py` can read it. owner: the next Makoto session.
   projection: `python3 tools/project.py 6 AUDIT.jsonl VERDICTS.tsv` (no model). The 09-28 record is
   `docs/v9/records/audit-3.3.0-2026-09-28.jsonl` with `docs/v9/records/verdicts-3.3.0-2026-09-28.tsv`:
   `PROJECT 6 checks=17 worth=5 not=12 fires=125`. The first 3.4.7 record, graded, is in
   `docs/v9/records/`: `PROJECT 6 checks=4 worth=2 not=2 fires=9`. Of the 12 rows only
   content.verifier_exit_masking fired there, and it still fails; its subtraction reverts C4 to
   NOT-COUNTABLE, which the step 7 ratchet forbids, so it is held for the owner (VOIDS). The other 11
   need a record where they fire. cap: 2 model calls and 5 minutes per VOIDS row.
   Stop: at the cap, record the measured number in VOIDS and go on.
7. ~~Build the ratchet and the shared pieces: `kit.neighbours`, O(n·t) with one token blanked, and
   `kit.claim`~~ (branch claude/pensive-carson-cbpr5j). gate.running_claim now reads its claim through
   `kit.claim`, and `_code_spans` moved down to `vocab` so kit can use it.
   check: `tests/test_ratchet.py` (its PIN, read off `tools/register_map.py`, falls with each row) and
   `tests/test_kit_shared.py`. plant: flip any RUNNER row back and the ratchet reads red; a pairwise
   loop in `kit.neighbours`, or no negation filter in `kit.claim`, and its test reads red.
   inputs: `docs/FOUNDATION-14.md`, "Shared pieces". owner: done.
8. (`docs/PRIOR-ART.md` item 3.) Rows B36, H4, E9, D8, B14, F12, A14, B18, B37, F6, B28 and G3,
   cheapest first, one commit each. Each commit lowers the pin by 1. A6 and E8 landed on branch
   claude/pensive-carson-cbpr5j as gate.gradient_collapse and gate.option_interaction (pin 18 to 16);
   `tests/test_gradient_collapse.py` and `tests/test_option_interaction.py` keep the 14 witnessed
   defects two Codex gpt-6-astra reads found in them.
   check: register_map moves the row to RUNNER; its catch test is red with the row removed;
   latency and worth stay green. plant: the catch case in the FOUNDATION-14 table for that row.
   inputs: each row's owes and paid-by are defined in the table. What each row still needs is
   its measured false rate on real sessions: `tools/corpus.py` over the transcripts in
   `~/.claude/projects/`. A fresh container holds no earlier sessions, so the step makes its own
   input: the running session's transcript (`~/.claude/projects/<cwd>/<session>.jsonl`, written
   from the first turn) is the floor, and `ls ~/.claude/projects/*/*.jsonl | wc -l` is counted
   first. A row with no fires on that floor records `fires=0` in VOIDS at the cap. B14's benefit verbs and D8's
   narrowing flags are settled by those corpus fires. Cheapest way: convert the corpus once and
   replay it once for all remaining rows and step 11's thresholds together, never once per row.
   Accept a row only on your own run of its catch test. owner: the next Makoto session.
   projection: `python3 tools/project.py 8` (no model) parses each row's v9 line with the
   evaluator: `PROJECT 8 lines=14 parsed=9 refused=5`. The 5 refused are not lines (Q: judgments and
   Countdown kernel notes); the parsed ones name, in VOIDS, the facts they still lack. cap: 8 model calls and 15 minutes per row.
   Stop: at the cap, record the measured number in VOIDS and go on.
9. ~~Cut the per-call start cost~~ (branch claude/pensive-carson-cbpr5j). Module-level patterns are
   `vocab._lazy_re`, compiled on first use: one Pre compiles 23 patterns instead of 206.
   check: `tests/test_hook_latency.py::test_no_module_level_regex_compile_outside_core` and
   `::test_one_pre_compiles_few_patterns` (bound 40). plant: a module-level `re.compile` added
   back reads red; both read red on 6cff354. inputs: `python3 -X importtime` on the Pre shim.
   owner: done.
10. ~~Close the shared mesh~~ (branch claude/pensive-carson-cbpr5j). `tools/mesh/` (from
   `handoff/MAKOTO/mesh` in Measure-Zero-Dev's `handoff.zip`) reads distance 0 over 165 cases and 44
   roots (2026-09-29: seven more, the three live false fires of that night as clean cases with their
   catch guards; `python3 tools/cover.py --check` states each check's width in `docs/COVERAGE.tsv`), and `proposed.tsv` (I1 to I3) reads 0. The last reds were stale cases, not rule gaps: a
   push with no verifier is now denied at Pre (gate.unverified_merge), `pytest || true` is caught
   first at Pre (content.verifier_exit_masking), the advisory tier was removed 2026-09-25, and a
   scratch `rm -rf` is exempt by design (the catch is now `rm -rf build` after a red run, with
   scratch and mktemp pass cases).
   check: `MAKOTO_ROOT=plugin python3 tools/mesh/mesh.py` prints `distance 0`. plant:
   `tools/mesh/harness.orig.py` as harness.py reads 17. inputs: `tools/mesh/`.
   owner: done.
11. Conduct rows J1 to J8, defined in `docs/CONDUCT.md` (`docs/PRIOR-ART.md` item 5): off-path acts, hand repeats, serial
    independent runs, duplicate shapes, unslotted units, re-reads, chunkable edits and small-call
    loops. Some of the conduct Gabriel requires is already live (the entries named in that file).
    These eight are not yet prevented.
    check: register_map carries each J row as RUNNER. plant: the catch case in its table row.
    inputs: the gap named on each row, which is a threshold to measure on `tools/corpus.py`, or an
    input that does not exist yet. The inputs that do not exist yet are the step-row reader (J1),
    the names index (J4), the mesh slot map (J5) and a recorded PreCompact event (J6).
    owner: the next Makoto session, after step 7's kit.neighbours.
    projection: `python3 tools/project.py 11` parses `docs/v9/conduct-lines.tsv` (one v9 line per J
    row): `PROJECT 11 lines=8 parsed=8 refused=0` since step 13's count(); J2 to J8's remaining facts
    and thresholds are step 11 rows in VOIDS. J4's names index exists as Scour's names ledger
    (`sh tools/scour.sh` prints `names=`), and J5's slot map as `MAKOTO/mesh/placement.tsv`. J1 (no
    step-row reader) and J6 (no recorded PreCompact event) have nothing to project from; they are
    step 11 rows in VOIDS. cap: 4 model calls and 10 minutes per row.
    Stop: at the cap, record the measured number in VOIDS and go on.
12. ~~One count and one owner per register entry~~ (branch claude/pensive-carson-cbpr5j;
    `docs/PRIOR-ART.md` items 1, 2 and 7). The count is read off `docs/REGISTER.md`, and the docs
    that typed it now point at the tool. `python3 tools/owners.py` joins `docs/REGISTER-MAP.tsv`
    with Scour's probes and declined() reasons at the `tools/scour.sh` pin into
    `docs/v9/owners.tsv` (the committed copy had drifted: G2, B4, E1 and F10 were NOT-COUNTABLE in
    the map and `makoto` or `both` in the table). `python3 tools/dedupe.py` runs B2, B7 and F2 both
    ways: each side is silent on the other's catch case, so each is one entry's two facets (Scour
    the tree, Makoto the event) and both stay; D1 is not a duplicate at the pin (Scour declines it).
    check: `tests/test_register_count.py`, `tests/test_owners.py`; with the clones,
    `python3 tools/owners.py` and `python3 tools/dedupe.py`. plant: a wrong count typed into
    README.md reads red; a RUNNER flipped in the map reads red. inputs: the Scour and Measure-Zero
    clones at the `tools/scour.sh` pins. owner: done.
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
    inputs: the v9 lines in `docs/v9/predicates.tsv`, and the round-nine cases in
    `docs/attack-round-nine.md`. owner: the next Makoto session.
    projection: `python3 tools/project.py 13` (no model; this checkout's evaluator) prints `PROJECT 13
    lines=77 parsed=69 refused=8`. Landed on branch claude/pensive-carson-cbpr5j: the evaluator with
    refs(), set difference, exists n, count(), contains and field values (`tests/test_line.py`), and
    the read ledger, fact builder and claim reader (`substrate/facts.py`; the dispatcher stamps each
    seen file's hash, `tests/test_facts.py`). The 8 refused are not lines (VOIDS names each missing
    fact). Owner's rulings (2026-09-28): G2, B4 and F10 stay unclaimed; each needs a fact no hook
    carries, and a live check covers its weaker reading (G2: gate.unasked_plan; B4:
    gate.unwitnessed_verifier; F10: gate.canon). The proving set is `docs/attack-round-nine.md`
    ("Attack round nine", 21 escapes over E3, E12, E11, C4, D14, and "round nine b", 58 entries),
    each case rebuilt from its shape as a plant red on main; each check's own test file is only the
    no-regression bar. cap: 6 model calls and 10 minutes per row. Landed 2026-09-29 (#118 to #122):
    `tests/test_round_nine.py` plants 192 cases over 58 entries (the 63 claimed, less G2, B4 and F10
    by ruling and A5 and A11, whose bases never reproduced), each red before its fix; each entry's
    live check was rewritten over its effect, since lines do not yet decide the same set as the
    checks (VOIDS `retire-into-lines`). Held out, with measured numbers: VOIDS `B21-rate`,
    `F8-dispatch`, `F8-rate`, `C2-claim`, `attack-cut`.
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
    (37+72 calls); Sonnet 5 0/6 at 109k+193k; Codex gpt-6-astra (high effort, `tools/codex_reader.py`,
    2026-09-28 22:1xZ) 3/6 at 1.75M+3.21M mostly cached (M11; M12 and S2 in kind; not H9, M13, S1);
    Opus 5.5 2/6 asked only the 8 unit-questions the
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
