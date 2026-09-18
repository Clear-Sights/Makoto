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
| H3 | `gate.pasted_fix` | #85 |

Two consolidations came out of scour's duplicate-name probe, both net subtractions: three
per-module advisory-posture tests became one whole-set law in `tests/test_check_law_tests.py`
(which found that `blocking_eligible`'s docstring was already inaccurate about
`gate.stale_establisher` and `gate.undeclared_falsifiable`), and four per-module
malformed-row tests became one whole-set law in `tests/test_stop_gate_level_invariant.py`
covering every history-eating gate. One architectural subtraction: the recorded per-test
verdict parsers moved from `checks/namedTestTeeth.py` to `vocab.py`/`kit.py`, their reachable
home, which deleted a documented lazy-import exception from
`tests/test_import_direction.py`'s `_CALL_TIME_OK`.

## What is left: nothing, for Makoto alone

H4 was the last entry the register mapped as UNCOVERED and in subject, and it closed as a
measured refusal rather than a runner. Nothing else is buildable: the remaining entries are
OUT-OF-SUBJECT or NOT-COUNTABLE with the reason written in their map row. The two sections
below are what shaped the last two verdicts, kept so neither is re-derived.

### H3 FIX DRAWN FROM FIXES — done, and the measurement that shaped it

`gate.pasted_fix` (Stop, ADVISE, PATTERN_MATCH, eats `history`): the same normalized block of
introduced text reaching a SECOND file with no verifier run between the two landings. Do not
re-derive the readings below; each was measured over this tree's own 185 non-merge commits, a
commit standing in for one session's introduced text.

* The NAIVE reading — two or more edits with no run between them — fires on 136 of 185, 73.5%.
  That is what writing code looks like, and it is why the candidate reading exists.
* Three narrowings, each with the rate it bought: the same text in two DISTINCT files
  (73.5 → 9.2%); `Edit`/`MultiEdit` only, because a fix changes what exists while a WRITTEN file
  carries the house import header (9.2 → 3.8%); and a block carrying a line that is not a
  comment, an import or a decorator (3.8 → 3.2%).
* The grain of four substantial lines is the same measurement: one line fires on 21.1%, eight on
  nothing at all. The recall bound follows — a repair shorter than four substantial lines is not
  a finding, and it fails quiet.
* It is NOT `kit.unmet_obligation_gate`: that factory's guard, once seen, pays for the rest of
  the session, and here the run must fall BETWEEN the two landings. `kit.ran_a_verifier` is the
  vocabulary, unchanged.
* `docs/MERGE-WITNESSES.tsv` carries the pair against `gate.unwitnessed_verifier` both ways; the
  witness input was measured rather than asserted, by running all thirty live Stop gates over it.

Thirteen plants, thirteen red, no holes, on a copy with the control green first.

### H4 SWEEP DRAWN FROM MEMORY — closed as a measured refusal

The handoff before this one named H4 the weakest of the five and said it may legitimately close
as a measured refusal rather than a runner, with the map row as its home. It did. Do not
re-derive this; the row carries it, and the short form is:

* The reading named as closest — a verdict naming N members of a set against a record showing
  reads of fewer than N distinct members — was built as a probe and run against a real Claude
  Code ledger, 29 turns carrying a claim. The counted-universal trigger matched 2. One fires,
  and it is a FALSE POSITIVE: `All 1086 ordered same-edge pairs refuted` was established by
  running `tools/merge_pass.py`, one command that checked all 1086, so the record holds 0
  distinct file reads.
* That is the fault's shape, not a threshold: in real work a claim over N items is discharged by
  a TOOL that examines the N items, so counting distinct reads against N is wrong by
  construction. The bulk-read discharge the previous handoff asked for does not save it, because
  `merge_pass.py`'s output names no paths at all.
* Repairing it means judging whether a tool's output COVERS a prose-named set: `F12`'s declined
  judgement, and the `gate.unnamed_failure` / `gate.named_test` overlap that handoff flagged.
* Outside the tree the fault is documented and not visible in a trace — the anchoring-in-LLM-
  judges measurement needs token log-probabilities a hook does not have, and published
  trace-audit tooling leaves quantified claims unaudited.

Reopen H4 if a corpus of real ledgers large enough to measure a rate becomes available. One
session cannot produce one, and that — not a preference — is what the row rests on.

## What a later run should know

No entry reads UNCOVERED. Every remaining one carries a verdict with its reason in its own map
row: RUNNER, OUT-OF-SUBJECT, or NOT-COUNTABLE. That is a real ceiling for Makoto alone rather
than a stopping point — the OUT-OF-SUBJECT rows name faults outside what a hook on one session's
record can see, and the NOT-COUNTABLE rows name faults that are in subject and that no countable
reading decides. Read the rows before assuming otherwise.

## How a runner lands

One PR per entry. Plants mutate a `shutil.copytree` copy, never the tree; the unmutated
control must be green before any plant is believed, and a plant that stays green is a hole in
the suite, not a pass. Report the measured numbers in the commit: plants red/holes, suite,
register map, merge pass, python lines before/after, and
`python3 -m scour . --register <measure-zero>/zero/resources/REGISTER.md --changed HEAD
--detail <a path OUTSIDE this tree>`. If a tool that report names is not available where you are
working, say so and report no number for it rather than an invented one.

A new gate touches more than its own module, and the suite names each one when you miss it:
`registry.py` (row and shape), `substrate/_declared.py`, `registry._ADVISORY_ALLOWLIST` if it
is ADVISE, `tests/test_gate_shape.py` (id set, module stems, file count, function counts),
`tests/test_dispatch.py` (a never-blocks pin), `tests/test_stop_gate_level_invariant.py` (a
scenario), `docs/REGISTER-MAP.tsv`, `docs/MERGE-WITNESSES.tsv`, `README.md`, and the two
plugin manifests. Pre-tier ADVISE is illegal (`kit.py` states it): an advisory check is a
Stop-tier gate.

The tree under `tests/` is the zero-false-positive certification record. It is the product,
not overhead; nothing here cuts it. (That line carried a line count until 2026-09-18, by which
point it had drifted 1,668 lines out of date — this page's own first rule is that numbers are
read off the tools, and a count written here is a number written here.)
