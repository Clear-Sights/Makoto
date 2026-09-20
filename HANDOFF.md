# Makoto — handoff

This page is written for someone with no history with this project and no particular
tooling. Every command below is plain `git`, `python3` and `pytest`. Nothing here needs
an AI assistant of any kind to read, run or continue, and no step assumes you have seen
any earlier conversation.

Read this page once, top to bottom, before changing anything. Then **read the numbers off
the tools, never off this page** — the commands that produce them are in §3.

> ### First: which repository are you looking at?
>
> This page is written from `Clear-Sights/makoto-dev`, and it is copied verbatim into
> `Clear-Sights/Makoto` by the publish script. Run `git remote -v` and check.
>
> * **`makoto-dev`** — you are in the source. Everything below applies. Make your change here.
> * **`Makoto`** — you are in the **published copy**, which is generated. A change made here
>   is overwritten by the next publish. Go to `Clear-Sights/makoto-dev` and work there.
>   Some paths this page names (`scripts/`, `tools/`, several `docs/` files) are excluded
>   from the publish and will not exist where you are standing.
>
> Wherever this page says "makoto-dev", it means that repository by name and not "the one
> you happen to have open".

---

## 1. What Makoto is

Makoto is a plugin for coding agents (Claude Code's hook interface today) that holds an
agent to its own logged record. When an agent says "the tests pass" or "I created the
file", Makoto checks that claim against what the session's own tool log actually shows,
and blocks the turn when the record contradicts it.

Two properties define it, and both are load-bearing:

* **It is passive.** It runs because the host fires a hook, not because a person chooses
  to run it. Anything that only catches a fault when a human remembers to run a command
  is not Makoto doing its job. See §5 — this is currently true of most of the tool and
  not all of it, and closing that gap is the main outstanding work.
* **Every blocking check ships at measured zero false positives** on the corpus in
  `tests/`. The tree under `tests/` is the certification record. It is the product, not
  overhead. Nothing here cuts it.

Python 3.11, 3.12 and 3.13 are supported. Standard library only in the plugin — no
network calls, no model calls, nothing that can hang the hook.

---

## 2. The repositories, and which one you change

There are four, and getting this wrong is the single most expensive mistake available.
It has already been made once: eleven days of work landed in the wrong repository and had
to be reconciled by hand.

| repository | what it is | do you edit it? |
|---|---|---|
| `Clear-Sights/makoto-dev` | **the source.** All development happens here. This file lives here. | **yes** |
| `Clear-Sights/Makoto` | the published copy, generated from `makoto-dev` | **no** |
| `Clear-Sights/measure-zero-dev` | the source of `REGISTER.md` (see §4) | no (different project) |
| `Clear-Sights/measure-zero` | the published copy of that | no |

`scripts/publish_public.sh`, in `makoto-dev`, is what generates the public copy. It
stages a curated subset of `makoto-dev`, runs the suite against the staged copy, and then
`rsync -a --delete`s it over a checkout of the public repository. **Do not run it** unless
the repository owner has asked for that specific publish. It is the only irreversible
action in this project. It has a pre-delete guard (`divergence_guard`, documented in
`docs/PUBLISH-RECONCILIATION.md` §3) that aborts loudly if the sync would destroy a
tracked path that exists only on the public side, so the failure mode is a refused
publish rather than lost work — but that is a safety net, not a licence.

**Current state of the divergence, as of 2026-09-20.** The public repository is *ahead*
of this one, which is backwards and is being corrected. Twelve checks are live there and
absent here. They are listed in §6, item 1. Until they are ported, a publish would be
refused by the guard, and that is correct.

---

## 3. How to run everything

From the root of a clean checkout of `makoto-dev`:

```sh
# create a virtualenv OUTSIDE the checkout. Inside it, its site-packages land in the
# repository and several tests that sweep the tree will fail for that reason alone.
python3 -m venv ../makoto-venv
../makoto-venv/bin/pip install pytest

# the suite — about 40 seconds
PYTHONPATH=$PWD/plugin ../makoto-venv/bin/python -m pytest -q

# every register entry graded, and every live check checked for a register home
PYTHONPATH=$PWD/plugin python3 tools/register_map.py

# every pair of checks proven distinct from every other
PYTHONPATH=$PWD/plugin python3 tools/merge_pass.py

# the README's check counts checked against the code
PYTHONPATH=$PWD/plugin python3 tools/render_checks.py --check
```

What "green" means for each:

* **suite** — every test passes. Expect one `xfail`; that is deliberate.
* **`register_map.py`** — exit 0 and the line `every entry carried, every runner real,
  every verdict explained`. It exits 2 if any entry has a verdict with no explanation.
* **`merge_pass.py`** — exit 0 and `every pair refuted; the check set is at a fixpoint`.
  Exit 1 means two checks are indistinguishable and one should be deleted. Exit 2 means a
  pair could not be decided and needs a row in `docs/MERGE-WITNESSES.tsv`. Re-run this
  after adding or widening **any** check: widening one entry can loosen another, so the
  whole grid re-runs, never just the row you touched.
* **`render_checks.py --check`** — the counts in `README.md` match the code.

Measured on this branch on 2026-09-20, on Python 3.11, 3.12 and 3.13:

```
suite          1981 passed, 1 xfailed, 45 subtests
register map   RUNNER 44, OUT-OF-SUBJECT 13, NOT-COUNTABLE 13, UNCOVERED 4; 74 rows / 74 entries
merge pass     38 checks, 716 ordered same-edge pairs, every one refuted
render_checks  counts match makoto.registry
```

A tool named `scour` appears in this project's older notes. It is not installed and is in
no repository reachable from a `makoto-dev` checkout. If you cannot run something this page names, **say so
and report no number for it** rather than inventing one.

---

## 4. The register, and what the four families mean

`docs/REGISTER.md` is a catalogue of 74 ways a claim can be wrong. It is **vendored** —
copied byte-for-byte from `Clear-Sights/measure-zero-dev/REGISTER.md`, which is its only
source. Do not edit it here. Re-vendoring is a deliberate act: copy the file, then update
`REGISTER_DIGEST` in `tests/test_register_pass.py` to the new SHA-256, which is the record
that a copy moved.

The register groups its entries into **four families**, by what a checker must have in
hand to catch them. The families are cumulative — each needs something the one before
does not:

1. **THE SPEC** — one reading, and a definition the checker already holds.
2. **THE OTHER POINT** — a second reading of the same thing; no definition held.
3. **THE SWITCH** — an act first: feed an input, then read the response.
4. **THE LINEAGE** — the readings themselves: what was read before the write.

An entry's letter (`A3`, `H4`) is only where it was born under an older eight-group
scheme. **The letter is not the family.** An entry lives under its shape.

`docs/REGISTER-MAP.tsv` gives every entry exactly one verdict, with a note that has to
say why:

* `RUNNER` — a named check, test or dispatch property enforces it. The note names it.
* `NOT-COUNTABLE` — in subject, but no countable reading decides it. The note says what
  comparison it would need.
* `OUT-OF-SUBJECT` — the fault lives in code Makoto does not execute or a system it does
  not configure.
* `UNCOVERED` — in subject, countable, and nothing enforces it yet. **This is the only
  verdict that names real work left**, so it is the one to look for first.

---

## 5. What the coverage actually is

This section exists because the map alone reads better than the truth. All four numbers
below are measured, and the commands are in §3.

### 5.1 Not everything is passive yet, and it should be

Of the 74 entries, in the **public** tree (which has the fuller check set):

* **50** are held by something that runs on its own at a hook edge — the live checks,
  plus the dispatcher's fail-closed path and the audit log.
* **6** are held only when a person runs a command: B7 and B21 by `tools/merge_pass.py`,
  B34 by `tools/register_map.py`, F2 by `tests/test_gate_shape.py`, B10 by the corpus
  false-positive invariant, E1 by `tests/test_stop_gate_level_invariant.py`.
* **18** have no runner at all (the `NOT-COUNTABLE` and `OUT-OF-SUBJECT` rows).

The six are concentrated in family 3, THE SWITCH — six of its twelve runners. That family
needs an act performed before anything can be read, and a hook that reads one session's
record cannot perform one. **That is a finding, not an acceptable design.** The owner's
stated intent is that Makoto is passive, so an entry held only by the suite is a gap
against intent, and the map reading `RUNNER` for those six overstates what happens when
nobody runs anything.

### 5.2 Checks are not gated by shape at the Stop edge

The owner's stated intent is that a check runs on its own shape and not on every event.
That is **true at the Pre edge and false at the Stop edge**:

* Pre: **every** Pre check declares `keywords` (15 of 15 here, 13 of 13 in public), and
  `dispatch._run_predicates` runs a check only when one of its keywords appears in the
  payload.
* Stop: `context.run_stop_checks` (`plugin/makoto/context.py:276` here, `:259` in public)
  iterates `sorted(load_checks(edge="Stop"))` and runs **every** Stop check on **every**
  Stop event. Only **2** Stop checks declare keywords at all (2 of 23 here, 2 of 32 in
  public), and nothing consults them on that path.

Reproduce:

```sh
PYTHONPATH=$PWD/plugin python3 -c "
from makoto import registry
for edge in ('Pre', 'Stop'):
    cs = [c for c in registry.load_checks() if c.applies_at == edge]
    print(edge, len(cs), 'checks,', len([c for c in cs if c.keywords]), 'declare keywords')"
```

Most Stop gates read the assistant's text and fall silent when there is no claim, so the
result is correct — but the work is done every time, and the design intent is not met.
Closing this means giving each Stop check an admission test the way the Pre catalogue
already has, and proving on the corpus that no gate that used to fire stops firing.

### 5.3 Fourteen checks depend on the wording of a claim

Of the 45 live checks in the public tree, **31 fire on the record alone** — rename
anything, reword anything, they still fire. The other **14 must first recognize a claim in
prose**. For those, coverage is in word rather than in spirit: phrase the claim outside
the lexicon and nothing fires.

Worse, the miss rate of those recognizers is **unmeasured**. The register has an entry for
exactly that fault — `B36 UNMATCHED RESIDUE UNREPORTED`, "a recognizer's misses vanish
instead of counting" — and it is marked `NOT-COUNTABLE`. Its map note argues that a turn
carries what matched and never the residue, which is true of *your* recognizers and not of
Makoto's own. Makoto could count its own misses. Until it does, "covered" for those 14
checks means "covered for the phrasings we thought of".

### 5.4 The check set is not minimal, and not proven minimal

* One check, `gate.relative_path_citation`, serves no register entry at all. It is
  declared in `OUTSIDE_THE_REGISTER` in `tools/register_map.py` with its reason. So with
  respect to the register, the set is provably non-minimal by exactly one.
* `merge_pass.py` proves that no check is subsumed by another **at the same edge**. It
  never compares a Pre check with a Stop check. Three entries — D1, E12 and G1 — are
  covered at both edges, and that overlap has never been tested for redundancy.
* 34 of the cited checks are named for exactly one entry each.

---

## 6. Open defects

Each is reproducible with the commands in §3 and named with a file and a line.

1. **Twelve checks exist in the public repository and not here.** `gate.pasted_fix`,
   `gate.relaunched_unchanged`, `gate.report_before_run`, `gate.unasked_plan`,
   `gate.unclaimed_unit`, `gate.undischarged_waiver`, `gate.unknown_ref_switch`,
   `gate.unnamed_failure`, `gate.unobserved_destruction`, `gate.unprobed_fanout`,
   `gate.unread_structure`, `gate.unwitnessed_verifier`. Seven of them rest on a factory,
   `kit.unmet_obligation_gate`, that `makoto-dev` also lacks. Porting them moves C11, C12, H3
   and H6 off `UNCOVERED` and eight further rows off `NOT-COUNTABLE`. **This is the next
   piece of work.**

2. **`gate.contract_order` is registered twice**, once at the Pre edge and once at Stop, so
   `registry.load_checks()` returns two different checks sharing one id. The public tree
   cut that module entirely. Reproduce:
   ```sh
   PYTHONPATH=$PWD/plugin python3 -c "
   import collections
   from makoto import registry
   c = collections.Counter(x.id for x in registry.load_checks())
   print({k: v for k, v in c.items() if v > 1})"
   ```

3. **This repository has no reverse audit.** The public tree's `register_map.py` also
   refuses the run when a live check is named nowhere in the map — a check enforcing no
   rule, which is entry `B7` pointed inward. Adding it here would immediately flag
   `content.deferred_checkbox_theater`, `gate.advance`, `gate.contract_order` and
   `gate.run_promised`, which this map names nowhere. Each needs a judgement, not a
   mechanical port.

4. **Three `NOT-COUNTABLE` verdicts look wrong** and should be re-argued or overturned:
   * `B37 SIMPLER FORM UNSOUGHT` — the map says it needs semantic equivalence, "which is a
     similarity judgement". The register's own fix line says the opposite: *an act proves
     them equal, not a reading.* `tools/merge_pass.py` already performs that act over
     Makoto's own check set, and `B21` cites it for doing so.
   * `A13 SETTING CALLED INHERENT` — the fix asks which layer set the value. That needs the
     record of whether the agent read the configuration layer, not access to the platform.
     The map's reason answers a question the fix does not ask.
   * `B36 UNMATCHED RESIDUE UNREPORTED` — see §5.3. This is the expensive one: it is what
     leaves the 14 prose-dependent checks unmeasured.

5. **The public tree's `H5` map row overclaims.** It says "every gating decision is
   persisted". `dispatch._record_audit` returns early when a run produces no finding — the
   only-fires policy stated in its own docstring — so a silent pass is persisted nowhere.
   Corrected in `makoto-dev`; the published copy still carries it and picks the correction up
   at the next publish.

---

## 7. What to do next, in order

**What finished looks like.** Every register entry carries a verdict that a runner can
falsify, or a written refusal that says what was measured and why the reading does not pay;
`register_map.py` reports `UNCOVERED 0` in **both** trees and refuses the run when a live
check is named nowhere; `merge_pass.py` reaches a fixpoint across edges, not only within
one; and no check that depends on the wording of a claim is shipped with its miss rate
unmeasured. The public tree reports `UNCOVERED 0` today and is **not** finished by this
definition — §5 says exactly which parts of it are not.

Each step below gives the action, why it comes where it does, and the observation that tells
you it worked. Steps 1 and 2 are ordered; 3, 4, 5 and 6 are independent of each other and of
1–2, so they can be taken in any order or in parallel by separate agents.

1. **Port the twelve checks in §6.1 into `makoto-dev`**, `kit.unmet_obligation_gate` first
   since seven of them need it. One pull request per register entry.
   *Why first:* every other dev-side number is misleading while dev is eight checks behind
   the tree it generates, and §6.3's reverse audit cannot be judged against a check set that
   is still moving.
   *Done when:* `python3 -c "from makoto import registry; print(len({x.id for x in registry.load_checks()}))"`
   reads the same in both trees, and the map rows for C11, C12, H3 and H6 move off
   `UNCOVERED`.

2. **Update the map rows the ported checks cover**, and re-run `register_map.py` in both
   trees.
   *Why here:* a ported check with no map row is invisible to the only tool that grades
   coverage, so step 1 is not actually banked until this lands.
   *Done when:* `UNCOVERED` falls in dev and neither tree gains a `stale` or `orphan` row.

3. **Add the reverse audit to `makoto-dev`** (§6.3) and home or declare the four checks it
   flags: `content.deferred_checkbox_theater`, `gate.advance`, `gate.contract_order`,
   `gate.run_promised`.
   *Why it is not a mechanical port:* the audit will flag all four immediately, and each one
   is a separate judgement — does it serve an entry that has no row yet, or does it serve no
   entry at all and belong in `OUTSIDE_THE_REGISTER` as `gate.relative_path_citation`
   already does?
   *Done when:* the audit runs and reports zero unhomed checks, with each of the four either
   carrying a map row or declared outside.

4. **Take on `B36`** (§5.3, §6.4).
   *Why it is the expensive one and worth it:* fourteen checks must recognise a claim in
   prose before they fire, and nothing measures how often they miss. Until that number
   exists, "covered in spirit" is an argument. `B36` is the register's own entry for exactly
   this fault and is currently marked `NOT-COUNTABLE`.
   *Done when:* a miss rate is measured on real ledgers and either the recognisers are
   improved or `B36`'s verdict is rewritten around the number.

5. **Re-argue `B37` and `A13`** (§6.4). Both may end as refusals again — that is a
   legitimate outcome — but the reasons currently written do not answer the questions the
   register's own fix lines ask.
   *Done when:* each row's reason addresses its fix line, whatever verdict it lands on.

6. **Fix the duplicate `gate.contract_order` id** (§6.2).
   *Why last:* it is small and isolated, and the public tree already cut the module, so
   nothing else waits on it.
   *Done when:* the reproduction in §6.2 prints `{}`.

Two things are **not** on this list and should not be added to it without the owner saying
so: shape-gating the Stop edge (§5.2), which is a design change large enough to be its own
decision, and running the publish script (§9).

---

## 8. Possibilities, and what has already been tried and refused

**Do not re-derive these.** Each was measured or decided in a previous round. Reopening one
is allowed; starting it over from scratch as if it were new is the waste this section exists
to prevent.

**Refused, with the reason:**

* **A second runner for a register entry that already has one.** Two sessions built `H3` in
  parallel; the other merged first as `gate.pasted_fix`. The whole second gate, its tests and
  its plants were dropped rather than shipped, because the project's rule is one runner per
  entry. If an entry already has a runner and you think it is weak, the move is to *harden
  that runner*, never to add a second.
* **Mechanically porting the public tree's reverse audit.** See §7.3 — the port is two lines,
  the four judgements it forces are the actual work.
* **"Fixing" the public register to match dev's.** Dev's `docs/REGISTER.md` was the stale
  copy (76 entries, no `H` family). The published copy, `measure-zero`'s copy and the
  vendored copy were byte-identical and correct. The direction of the repair is always dev
  ← public for the register, and dev → public for everything else.
* **Closing `H4` with a runner.** It closed as a *measured refusal* instead: the map row
  carries the numbers. A refusal with a measurement in it is a real verdict here, not a
  failure to finish, and several rows already are one.

**Possibilities not yet taken, each with what it would cost:**

* **Shape-gate the Stop edge** (§5.2). The Pre edge already does this — all its checks
  declare `keywords` and only run when one hits the payload. At Stop, `context.run_stop_checks`
  runs every check on every Stop event and only two declare keywords at all. Closing it means
  giving ~21 checks a shape and proving each still fires on its own. This is the single
  largest gap between what the tool does and the stated intent that it is passive and
  per-shape.
* **Prove the check set minimal across edges, not only within one.** `merge_pass.py` refutes
  every ordered pair *within* an edge. `D1`, `E12` and `G1` are covered at both Pre and Stop
  and that overlap has never been tested. Extending the pass to cross-edge pairs is a change
  to one tool, not to any check.
* **Give the 18 no-runner rows a second look.** They are the not-countable and
  out-of-subject rows. Some are genuinely out of subject; the `B36`/`A13`/`B37` re-argument
  in §7.4–5 may show the classification is looser than it reads.
* **Harden the merged `gate.pasted_fix`.** Open question, never answered — see §9.
* **Carry the whole thing back to `measure-zero`'s register.** Makoto vendors
  `docs/REGISTER.md` byte-for-byte from `measure-zero`. A verdict changed here that implies
  the register's own text is wrong is a change to that repository, not this one.

---

## 9. Decisions only the owner can make

Do not take these on your own initiative, whatever a task description seems to imply.

1. **Running `scripts/publish_public.sh`.** It is an `rsync -a --delete` from a staged copy
   of `makoto-dev` onto a checkout of the public repository, and it is the only irreversible
   action in this project. "Push and merge" is pull-request language and does **not**
   authorise it. `divergence_guard` will abort it and name every path that would be lost —
   read that list rather than overriding it. The owner has to name this sync specifically.
2. **Whether to harden `gate.pasted_fix`** or leave it as merged. Asked, not yet answered.
3. **Whether the Stop edge gets shape-gated** (§8), and whether the resulting behaviour
   change is acceptable.
4. **Whether a prose-dependent check may ship at all** once `B36` puts a number on the miss
   rate. That is a standard, not a measurement.

---

## 10. What this environment does not have

Stated because each one costs a session an hour to rediscover, and because every one of them
reads as something other than "the tool is missing".

* **A fresh container is not provisioned.** Assume nothing is installed until you have
  checked. `pyproject.toml` declares `dependencies = []` and continuous integration installs
  pytest ad hoc.
* **Create the virtualenv OUTSIDE the checkout.** If pytest lands in a `.venv` inside the
  tree, `tests/test_rename_completeness.py::test_no_residual_old_taxonomy_names` fails —
  it greps every `*.py` under the repository root and matches third-party site-packages. The
  failure looks exactly like a real regression in the certification record. Run
  `git checkout uv.lock` afterwards; `uv pip install` dirties it.
* **`scour` is not installed and is in no repository you can reach.** Older notes cite it.
  If something asks you for a scour number, say it could not be run and report no number.
  Inventing one is worse than the gap.
* **`makoto-dev`'s continuous integration has been red since 2026-08-16** for reasons no diff
  can fix: jobs finish in three to five seconds and their logs return HTTP 404, meaning they
  were never assigned a runner. The same is true on `main`. The public repository's
  continuous integration is real and does run. Never re-run a `makoto-dev` job to "see if it
  passes" — a job that is never assigned a runner tells you nothing on the second attempt
  either.
* **Nothing in a checkout tells you which repository you are standing in.** Run
  `git remote -v` first, every time. See §2.

---

## 11. Rules that bind any change

* **One pull request per register entry.** A change that touches two entries is two
  changes.
* **Measure before you write code.** Establish the rate of the naive reading on real data
  first. A check that fires on most turns points at nothing. If a reading cannot be made
  to pay, refuse it with the measurement written into its map row — that is a legitimate
  outcome and there are several in the map already.
* **Plants, on a copy, with a green control.** To believe a test has teeth, copy the tree
  (`shutil.copytree`, keeping `.git` and symlinks), confirm the unmutated copy is green,
  then mutate one condition and confirm the test goes red. **A plant that stays green is a
  hole in the suite, not a pass.**
* **Report measured numbers in the commit message** — plants red and holes found, suite,
  register map, merge pass. Never a number you did not run.
* **A new check touches more than its own module**, and the suite will name each one you
  miss: `registry.py` (its row and its result shape), `substrate/_declared.py`,
  `registry._ADVISORY_ALLOWLIST` if it is ADVISE, `tests/test_gate_shape.py` (id set,
  module stems, file and function counts), `tests/test_dispatch.py`,
  `tests/test_stop_gate_level_invariant.py`, `docs/REGISTER-MAP.tsv`,
  `docs/MERGE-WITNESSES.tsv`, `README.md`, and the two plugin manifests.
* **An advisory check is a Stop-tier check.** ADVISE before the Stop edge is illegal and
  `kit.py` says so.
* **Never grade a row by reading it.** `docs/REGISTER-MAP.tsv` is a set of claims, and
  checking a claim by re-reading the claim is register entry `H1`. Read what the code
  does. The overclaim in §6.5 was found that way and would not have been found any other.
* **Continuous integration in `makoto-dev` has been red since 2026-08-16** for reasons
  unrelated to any diff: jobs finish in seconds without ever being assigned a runner. It
  is not yours to fix. **The local suite is the gate.** Say so plainly when you report a
  change rather than implying CI passed.
