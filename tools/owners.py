#!/usr/bin/env python3
"""One owner per register entry, by script (START step 12): join docs/REGISTER-MAP.tsv (Makoto's
dynamic runner per entry) with Scour's static probes and its declined() reasons, both read out of
the Scour clone at the pin tools/scour.sh names, into docs/v9/owners.tsv.

usage: python3 tools/owners.py [--write]
Without --write it compares the generated table with the committed one and exits 1 on any
difference; exits 2 with a LAUNCH MISSING line when the Scour clone or its pin is absent.
Owner is `both` (a Scour probe and a Makoto RUNNER), `makoto`, `scour`, or `none`.
"""
from __future__ import annotations

import csv
import importlib
import io
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAP = REPO / "docs" / "REGISTER-MAP.tsv"
OUT = REPO / "docs" / "v9" / "owners.tsv"
# Entries both own that tools/dedupe.py has run both ways: each side is silent on the other's catch
# case, so they are one entry's two facets (Scour the tree, Makoto the event), not a duplicate.
WITNESSED = ("B2", "B7", "F2")
SCOUR_PIN = next(ln.split("=", 1)[1].strip() for ln in (REPO / "tools" / "scour.sh").read_text().splitlines()
                 if ln.startswith("SCOUR_PIN="))


def missing(what: str):
    print(f"LAUNCH MISSING owners: {what}")
    sys.exit(2)


def scour_at_pin():
    """(probed ids, {declined id: reason}) from Scour at SCOUR_PIN, extracted to a temp dir."""
    clone = next((p for p in (REPO.parent / "Scour", REPO.parent / "scour") if p.is_dir()), None)
    if clone is None:
        missing("attach Clear-Sights/Scour with add_repo and clone it beside this repository")
    tar = subprocess.run(["git", "-C", str(clone), "archive", SCOUR_PIN], capture_output=True)
    if tar.returncode:
        missing(f"run git -C {clone} fetch origin {SCOUR_PIN}")
    d = tempfile.mkdtemp()
    tarfile.open(fileobj=io.BytesIO(tar.stdout)).extractall(d, filter="data")
    sys.path.insert(0, d)
    probes = importlib.import_module("scour.probes")
    return {p.id for p in probes.catalogue()}, probes.declined()


def table(probed: set, declined: dict) -> list[list[str]]:
    rows = [r for r in csv.reader(MAP.open(encoding="utf-8"), delimiter="\t")][1:]
    out = []
    for r in rows:
        if not r or not r[0].strip():
            continue
        entry, verdict, runner = r[0], r[1], r[2]
        run, probe = verdict == "RUNNER", entry in probed
        if run and probe and entry in WITNESSED:
            out.append([entry, "both", f"by facet: Scour probes the tree, Makoto runs the event ({runner}); "
                                       "each is silent on the other's case (tools/dedupe.py)"])
        elif run and probe:
            out.append([entry, "both", f"duplication: probed by Scour and run by Makoto ({runner}); keep one"])
        elif run:
            out.append([entry, "makoto", ""])
        elif probe:
            out.append([entry, "scour", ""])
        else:
            why = declined.get(entry, "no probe")
            out.append([entry, "none", f"blindspot: no runner, and Scour declines it: {why}"])
    return out


def render(rows) -> str:
    return "".join("\t".join(r) + "\n" for r in rows)


def main(argv) -> int:
    probed, declined = scour_at_pin()
    text = render(table(probed, declined))
    if "--write" in argv:
        OUT.write_text(text, encoding="utf-8")
        return 0
    if OUT.read_text(encoding="utf-8") != text:
        print("OWNERS: docs/v9/owners.tsv differs from the join; run python3 tools/owners.py --write")
        return 1
    print("OWNERS: docs/v9/owners.tsv is the join of REGISTER-MAP.tsv and Scour at " + SCOUR_PIN)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
