#!/usr/bin/env python3
"""Run the register's MERGING protocol over makoto's own check set.

A merge is a claim that one check's fix catches another's incident. The protocol's
step 1 demands the refutation, not the assertion: name an input that trips the
dropped check, apply the survivor alone, and show it passes.

This runner enumerates every ordered pair of checks that share an `applies_at`
edge and refutes each one, by the cheapest sound discriminant that applies:

  READS   the dropped check reads a channel the survivor does not. The survivor
          cannot decide an input it cannot see, so it cannot catch that input.
          Machine-checked: `eats` is enforced against the check body by
          tests/test_check_law_eats.py, so this is structural, not asserted.

  VOCAB   both checks declare a dispatch prefilter and the two are disjoint. A
          check fires only on input containing one of its keywords, and the
          prefilter is a declared superset of what the body can match, so no
          single input trips both.

  WITNESS neither structural discriminant applies, so the pair needs step 1 done
          by hand: a named input in docs/MERGE-WITNESSES.tsv that trips the
          dropped check and that the survivor passes.

A pair with no discriminant and no witness is NOT-EVALUABLE, and NOT-EVALUABLE
is not a pass: it exits 2. Exit 1 means a merge stands and the check set should
shrink. Exit 0 means every pair is refuted and the set is at a fixpoint.

Re-run this after adding or widening any check. The protocol's step 3 is the
reason: widening one entry can loosen another, so the whole grid re-runs, never
just the edited row.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin"))
WITNESSES = ROOT / "docs" / "MERGE-WITNESSES.tsv"

from makoto import registry  # noqa: E402


def load_witnesses(live_ids):
    """Read the witness table, and hold it to the live check set.

    A witness names a dropped check and the survivors it refutes. Both are check
    ids, so both can rot: a check is deleted and its witness row outlives it, or
    a survivor is renamed and the row still names the old id. Neither rots
    loudly on its own -- an orphan row is simply never consulted, and an unknown
    survivor name simply never matches -- so the table would keep asserting
    refutations for pairs that no longer exist. That is register entry F3, a
    referent that moved since it was named, and D13, acting on a set nobody
    re-listed. Both are checked here rather than trusted.
    """
    rows, errors = {}, []
    lines = WITNESSES.read_text(encoding="utf-8").splitlines()
    for n, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        dropped, survivors, witness = line.split("\t")
        if not witness.strip():
            errors.append(f"line {n}: witness row for {dropped} names no input")
        if dropped in rows:
            errors.append(f"line {n}: {dropped} has two witness rows")
        if dropped not in live_ids:
            errors.append(f"line {n}: witness names {dropped}, which the registry no longer carries")
        for s in survivors.split():
            if s not in live_ids:
                errors.append(f"line {n}: {dropped}'s row names survivor {s}, which the registry does not carry")
        rows[dropped] = (survivors.split(), witness)
    return rows, errors


def main():
    checks = registry.discover()
    witnesses, stale = load_witnesses({c.id for c in checks})
    reads, vocab, by_witness, unrefuted = 0, 0, 0, []

    for survivor in checks:
        for dropped in checks:
            if survivor.id == dropped.id or survivor.applies_at != dropped.applies_at:
                continue
            s_eats = survivor.eats or frozenset()
            d_eats = dropped.eats or frozenset()
            if not d_eats <= s_eats:
                reads += 1
                continue
            s_kw, d_kw = set(survivor.keywords), set(dropped.keywords)
            if s_kw and d_kw and not (s_kw & d_kw):
                vocab += 1
                continue
            row = witnesses.get(dropped.id)
            if row and (survivor.id in row[0]):
                by_witness += 1
                continue
            unrefuted.append((survivor.id, dropped.id))

    total = reads + vocab + by_witness + len(unrefuted)
    print(f"MERGE PASS  checks={len(checks)}  ordered same-edge pairs={total}")
    print(f"  refuted by READS   {reads}")
    print(f"  refuted by VOCAB   {vocab}")
    print(f"  refuted by WITNESS {by_witness}")
    if stale:
        print(f"  STALE WITNESSES    {len(stale)}")
        for e in stale:
            print(f"    {e}")
    if unrefuted:
        print(f"  NOT-EVALUABLE      {len(unrefuted)}")
        for s, d in unrefuted:
            print(f"    survivor={s} dropped={d}  -- no discriminant, no witness")
    if stale or unrefuted:
        return 2
    print("MERGE PASS: every pair refuted; the check set is at a fixpoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
