#!/usr/bin/env python3
"""Each check's stated width: how much of its fault the shared mesh shows it covering, and what
it states it does not (standard library only, no model).

usage: python3 tools/cover.py           -> writes docs/COVERAGE.tsv
       python3 tools/cover.py --check   -> exit 1 when docs/COVERAGE.tsv is not what the mesh reads now

One row per check in the catalog:
  fire       variants of the fault the mesh plants for it (catch, rewordings), caught / planted
  pass       look-alikes that must stay silent, silent / planted
  voids      register entries it runs for whose remainder `docs/v9/VOIDS.tsv` states as open
  width      measured (every planted variant caught, every look-alike silent), partial, or
             unmeasured (the mesh plants nothing for it: its width is unknown, and says so)
Anything not in `fire` is outside what the check is shown to see.
"""
from __future__ import annotations

import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MESH = REPO / "tools" / "mesh"
OUT = REPO / "docs" / "COVERAGE.tsv"


def rows() -> list[str]:
    os.environ.setdefault("MAKOTO_ROOT", str(REPO / "plugin"))
    sys.path[:0] = [str(REPO / "plugin"), str(MESH)]
    import mesh
    from makoto.registry import load_checks

    cases = list(csv.DictReader(open(MESH / "mesh.tsv"), delimiter="\t"))
    with ThreadPoolExecutor(8) as ex:
        got = list(ex.map(mesh.one, cases))
    entries: dict[str, list[str]] = {}
    for r in csv.DictReader(open(REPO / "docs" / "REGISTER-MAP.tsv"), delimiter="\t"):
        if r["runner"]:
            entries.setdefault(r["runner"], []).append(r["entry"])
    voids = {r["item"] for r in csv.DictReader(open(REPO / "docs" / "v9" / "VOIDS.tsv"), delimiter="\t")}
    out = ["check\tfire\tpass\tvoids\twidth"]
    for cid in sorted(c.id for c in load_checks()):
        fire = [g for r, g in got if r["root"] == cid and r["expect"] == "FIRE"]
        calm = [g for r, g in got if r["root"] == cid and r["expect"] == "ALLOW"]
        caught, silent = fire.count("FIRE"), calm.count("ALLOW")
        open_ = sorted(e for e in entries.get(cid, ()) if e in voids)
        if not fire:
            width = "unmeasured"
        elif caught == len(fire) and silent == len(calm):
            width = "measured"
        else:
            width = "partial"
        out.append(f"{cid}\t{caught}/{len(fire)}\t{silent}/{len(calm)}\t{','.join(open_) or '-'}\t{width}")
    return out


def main(argv: list[str]) -> int:
    body = "\n".join(rows()) + "\n"
    if argv[1:] == ["--check"]:
        if not OUT.exists() or OUT.read_text() != body:
            print("COVERAGE STALE: run python3 tools/cover.py")
            return 1
        print("COVERAGE current")
        return 0
    OUT.write_text(body)
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
