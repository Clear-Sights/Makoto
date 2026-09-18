# Makoto — where the work is

The standing rules and the catalog are elsewhere: `README.md` describes the tool,
`docs/CATALOG.md` the checks, `docs/REGISTER-MAP.tsv` the verdict per register entry.
This file is the only statement of what is left. **Read the numbers off the tools, never
off this page** — the three commands that produce them are below.

## The job

Tie Makoto to the 74-entry blindspot register (`docs/REGISTER.md`, vendored byte-identical
from `clear-sights/measure-zero`'s `zero/resources/REGISTER.md`), and cut what the coverage
does not need. Coverage was 44 of 74 when this run opened.

    PYTHONPATH=$PWD/plugin python3 tools/register_map.py    # per-entry verdict + reverse audit
    PYTHONPATH=$PWD/plugin python3 tools/merge_pass.py      # every ordered pair refuted
    PYTHONPATH=$PWD/plugin python3 -m pytest -q             # the suite

`register_map.py` grades `docs/REGISTER-MAP.tsv` and runs the reverse audit: every live
check must be cited by a map row or declared outside the register with a reason. A homeless
check refuses the run.

## What landed

Nine entries Keel and Ward ran and Makoto lacked: eight built, one refused with a
measurement (E8 OPTION INTERACTION — the map row carries the reason; do not re-derive it).
Seven of the eight are `ACT_VS_GUARD`, a result shape built on `kit.unmet_obligation_gate`
and ported by shape from Keel's `plugin/keel/clauses.json`.

| entry | runner | PR |
|---|---|---|
| B11, G2 | `gate.unprobed_fanout`, `gate.unasked_plan` | #79 |
| A3, B4, D12, D14, E13 | `gate.unread_structure`, `gate.unwitnessed_verifier`, `gate.unknown_ref_switch`, `gate.unobserved_destruction`, `gate.relaunched_unchanged` | #80 |
| B9 | `gate.undischarged_waiver` | #81 |
| C12 | `gate.unnamed_failure` | #82 |
| C11 | `gate.report_before_run` | #83 |
| H6 | `gate.unclaimed_unit` | #84 |

Two consolidations came out of scour's duplicate-name probe, both net subtractions: three
per-module advisory-posture tests became one whole-set law in `tests/test_check_law_tests.py`
(which found that `blocking_eligible`'s docstring was already inaccurate about
`gate.stale_establisher` and `gate.undeclared_falsifiable`), and four per-module
malformed-row tests became one whole-set law in `tests/test_stop_gate_level_invariant.py`
covering every history-eating gate. One architectural subtraction: the recorded per-test
verdict parsers moved from `checks/namedTestTeeth.py` to `vocab.py`/`kit.py`, their reachable
home, which deleted a documented lazy-import exception from
`tests/test_import_direction.py`'s `_CALL_TIME_OK`.

## What is left: H3 and H4

These are the last two the register maps as UNCOVERED and in subject. Nothing else is
buildable — the honest ceiling for Makoto alone is 57, and the remaining entries are
OUT-OF-SUBJECT or NOT-COUNTABLE with the reason written in their map row.

### H3 FIX DRAWN FROM FIXES

*"a change reasoned from other changes"* > *"order by dependence; one change per pass"*.

The candidate reading, which the ledger can decide: **the same introduced text landing in
two or more distinct files with no verifier run between them** — one fix pasted across
sites, each site's correctness inferred from the first rather than checked. The naive
reading (N edits with no run between them) is indiscriminate and must not be built; measure
its rate on this tree's own ledgers before writing a line.

Plant rows it needs, each red on a copy with the control green:

- the distinct-file requirement dropped, so two edits to one file fire
- the verifier-run discharge dropped, so a run between the two edits no longer clears it
- the identical-text requirement widened to any two edits, so the gate is indiscriminate
- whatever normalization is chosen (whitespace, indentation) removed, so a reindented paste escapes
- the gate silenced entirely
- the advisory allowlist entry removed, so an ADVISE gate is published as blocking
- malformed-row tolerance removed — caught by the whole-set law, not a per-module copy

The merge pass compares same-edge pairs, so the survivor to refute is
`gate.unwitnessed_verifier`, which also discharges on a verifier run; the answer belongs in
`docs/MERGE-WITNESSES.tsv` as a row per survivor, or the pair is unrefuted and
`merge_pass.py` exits 2. The nearest prose neighbour, `event.thrash_revert`, is a pre-tier
check on a different edge and is never paired with it, so the distinction has to be written
down rather than left to the tool.

### H4 SWEEP DRAWN FROM MEMORY

*"each item read through prior conclusions"* > *"judge once up front; each read a token"*.

The weakest of the five, and **it may close as a measured refusal rather than a runner** —
that is a legitimate outcome, and the map row is where it goes, with the numbers that refused
it. Readings tried on paper:

- read-count against claim-count: FP-prone by construction, a bulk `grep -r` legitimately
  reads hundreds of files without claiming anything about them
- a verdict sentence naming N members of a set where the record shows reads of fewer than N
  distinct members: closest to the entry, and the one worth measuring first. Its risk is
  `gate.unnamed_failure` and `gate.named_test`, which already read a claim against the
  record — establish the READS or VOCAB difference before building, not after

Measure a rate on real ledgers first. A probe firing on every sweep points at nothing in
particular.

## How a runner lands

One PR per entry. Plants mutate a `shutil.copytree` copy, never the tree; the unmutated
control must be green before any plant is believed, and a plant that stays green is a hole in
the suite, not a pass. Report the measured numbers in the commit: plants red/holes, suite,
register map, merge pass, python lines before/after, and
`python3 -m scour . --register <measure-zero>/zero/resources/REGISTER.md --changed HEAD
--detail <a path OUTSIDE this tree>`.

A new gate touches more than its own module, and the suite names each one when you miss it:
`registry.py` (row and shape), `substrate/_declared.py`, `registry._ADVISORY_ALLOWLIST` if it
is ADVISE, `tests/test_gate_shape.py` (id set, module stems, file count, function counts),
`tests/test_dispatch.py` (a never-blocks pin), `tests/test_stop_gate_level_invariant.py` (a
scenario), `docs/REGISTER-MAP.tsv`, `docs/MERGE-WITNESSES.tsv`, `README.md`, and the two
plugin manifests. Pre-tier ADVISE is illegal (`kit.py` states it): an advisory check is a
Stop-tier gate.

The 22,835 lines under `tests/` are the zero-false-positive certification record. They are
the product, not overhead; nothing here cuts them.
