#!/usr/bin/env python3
"""Grade makoto's coverage of the blindspot register.

docs/REGISTER.md is a vendored copy; the source is measure-zero-dev/REGISTER.md.
docs/REGISTER-MAP.tsv gives every entry in it one of three verdicts:

  RUNNER          a named check, test or dispatch property enforces the entry
  NOT-COUNTABLE   the entry is makoto's subject -- the agent's own writes, commands and
                  claims -- but no reading of the record separates an instance from correct
                  work. The note names the closest reading tried and what defeats it: a
                  counterexample it fires on, a fact no hook payload carries, or a
                  similarity judgement, which makoto refuses.
  UNCOVERED       the entry is in makoto's subject and countable, and no check enforces
                  it yet. The note says what it would take.

This runner checks the map against the register and against the live registry:
every entry carried, no entry invented, every cited check id real, every row's
note non-empty. A verdict with no note is NOT-EVALUABLE and exits 2 -- an
unexplained NOT-COUNTABLE is how a gap becomes invisible.

It also checks the OTHER direction, which nothing checked until 2026-09-18: every
live check must have a register home. A check the map names nowhere -- not in a
runner column, not in a note -- is a runner bound to no rule, which is `B7 RULE
WITH NO RUNNER` pointed inward, and it is how a check accumulates with no reason
to exist. A check that genuinely serves no entry is DECLARED in
`OUTSIDE_THE_REGISTER` below with the reason, which is `B35 UNDECLARED EXEMPTION`
applied to this tool's own exemptions.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin"))
REGISTER = ROOT / "docs" / "REGISTER.md"
MAP = ROOT / "docs" / "REGISTER-MAP.tsv"
VERDICTS = {"RUNNER", "NOT-COUNTABLE", "UNCOVERED"}
ENTRY_RX = re.compile(r"^([A-H]\d+)\s+[A-Z]")

# Live checks that serve no register entry, each with the reason it serves none. Adding a
# name here is a visible act: the reason is graded non-empty, the name must be a live check,
# and a name that the map ALSO cites is refused -- a check is either in the register's subject
# or declared outside it, never both.
OUTSIDE_THE_REGISTER = {}

from makoto import registry  # noqa: E402


def main():
    entries = [m.group(1) for m in
               (ENTRY_RX.match(ln) for ln in REGISTER.read_text(encoding="utf-8").splitlines())
               if m]
    live = {c.id for c in registry.discover()}

    rows, errors = {}, []
    for n, line in enumerate(MAP.read_text(encoding="utf-8").splitlines()[1:], start=2):
        if not line.strip():
            continue
        entry, verdict, runner, note = line.split("\t")
        if entry in rows:
            errors.append(f"line {n}: {entry} stated twice")
        rows[entry] = (verdict, runner, note)
        if verdict not in VERDICTS:
            errors.append(f"line {n}: {entry} verdict {verdict!r} is not one of {sorted(VERDICTS)}")
        if not note.strip():
            errors.append(f"line {n}: {entry} has a verdict and no note")
        if verdict == "RUNNER":
            if runner.startswith(("gate.", "content.", "event.")) and runner not in live:
                errors.append(f"line {n}: {entry} cites {runner}, which the registry does not carry")
            elif "/" in runner and not (ROOT / runner).exists():
                errors.append(f"line {n}: {entry} cites {runner}, which is not on disk")
        elif runner != "-":
            errors.append(f"line {n}: {entry} is {verdict} but names a runner")

    for missing in sorted(set(entries) - set(rows)):
        errors.append(f"register entry {missing} has no row in the map")
    for invented in sorted(set(rows) - set(entries)):
        errors.append(f"map row {invented} is not an entry in the register")

    # Every live check needs a register home. Word-boundary match, so `gate.canon` cited for
    # F10 does not silently satisfy `gate.canon_fingerprints`.
    map_text = MAP.read_text(encoding="utf-8")
    cited = {c for c in live if re.search(rf"(?<![\w.]){re.escape(c)}(?![\w.])", map_text)}
    for homeless in sorted(live - cited - set(OUTSIDE_THE_REGISTER)):
        errors.append(f"live check {homeless} is named nowhere in the map and is not declared "
                      f"in OUTSIDE_THE_REGISTER")
    for name, reason in sorted(OUTSIDE_THE_REGISTER.items()):
        if name not in live:
            errors.append(f"OUTSIDE_THE_REGISTER names {name}, which the registry does not carry")
        if not reason.strip():
            errors.append(f"OUTSIDE_THE_REGISTER declares {name} with no reason")
        if name in cited:
            errors.append(f"{name} is declared outside the register and cited inside it")

    counts = {v: sum(1 for r in rows.values() if r[0] == v) for v in sorted(VERDICTS)}
    print(f"REGISTER MAP  register entries={len(entries)}  rows={len(rows)}")
    for v, c in counts.items():
        print(f"  {v:<15s} {c}")
    print(f"  checks cited    {len(cited)} of {len(live)}")
    print(f"  declared outside {len(OUTSIDE_THE_REGISTER)}")
    if errors:
        print(f"  NOT-EVALUABLE   {len(errors)}")
        for e in errors:
            print(f"    {e}")
        return 2
    print("REGISTER MAP: every entry carried, every runner real, every verdict explained, "
          "every check homed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
