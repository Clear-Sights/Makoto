#!/usr/bin/env python3
"""Grade makoto's coverage of the blindspot register.

docs/REGISTER.md is a vendored copy; the source is measure-zero-dev/REGISTER.md.
docs/REGISTER-MAP.tsv gives every entry in it one of three verdicts:

  RUNNER          a named check, test or dispatch property enforces the entry
  NOT-COUNTABLE   the entry is in makoto's subject -- a statement graded against
                  the record -- but its test would be a similarity judgement, and
                  makoto refuses those. The note says which comparison it needs.
  OUT-OF-SUBJECT  the entry governs code makoto does not execute or a system it
                  does not configure. Not a gap in makoto; a gap in nothing.

This runner checks the map against the register and against the live registry:
every entry carried, no entry invented, every cited check id real, every row's
note non-empty. A verdict with no note is NOT-EVALUABLE and exits 2 -- an
unexplained NOT-COUNTABLE is how a gap becomes invisible.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin"))
REGISTER = ROOT / "docs" / "REGISTER.md"
MAP = ROOT / "docs" / "REGISTER-MAP.tsv"
VERDICTS = {"RUNNER", "NOT-COUNTABLE", "OUT-OF-SUBJECT"}
ENTRY_RX = re.compile(r"^([A-G]\d+)\s+[A-Z]")

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

    counts = {v: sum(1 for r in rows.values() if r[0] == v) for v in sorted(VERDICTS)}
    print(f"REGISTER MAP  register entries={len(entries)}  rows={len(rows)}")
    for v, c in counts.items():
        print(f"  {v:<15s} {c}")
    if errors:
        print(f"  NOT-EVALUABLE   {len(errors)}")
        for e in errors:
            print(f"    {e}")
        return 2
    print("REGISTER MAP: every entry carried, every runner real, every verdict explained.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
