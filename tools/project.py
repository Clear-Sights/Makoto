#!/usr/bin/env python3
"""Run one open START step's projection: its wiring mocked from pieces that exist, no model call,
no network. Prints one `PROJECT <step> ...` line and exits 0 when it ran; exits 2 with a
`LAUNCH MISSING` line naming the act when an input is absent.

usage: python3 tools/project.py 6 AUDIT.jsonl VERDICTS.tsv
       python3 tools/project.py 8|11|13 [REV]   (REV holds the evaluator; default this checkout)
       python3 tools/project.py 12
"""
from __future__ import annotations

import csv
import importlib.util
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
V9 = REPO / "docs" / "v9"
EVALUATOR_REV = "tree"
STEP8 = "B36 H4 E9 D8 B14 F12 A14 B18 B37 F6 B28 A6 G3 E8".split()


def missing(what: str) -> None:
    print(f"LAUNCH MISSING {what}")
    sys.exit(2)


def rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8") as f:
        return [r for r in csv.reader(f, delimiter="\t") if r and not r[0].startswith("#")]


def evaluator(rev: str):
    """The evaluator module at `rev`, read out of git so no checkout of its branch is needed;
    `tree` is the one in this checkout."""
    if rev == "tree":
        sys.path.insert(0, str(REPO / "plugin"))
        from makoto.substrate import line
        return line
    got = subprocess.run(["git", "-C", str(REPO), "show", f"{rev}:plugin/makoto/substrate/line.py"],
                         capture_output=True, text=True)
    if got.returncode:
        missing(f"evaluator at {rev}: git fetch origin claude/register-evaluator")
    src = Path(tempfile.mkdtemp()) / "line.py"
    src.write_text(got.stdout, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("register_line", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_lines(entries: set[str] | None, rev: str, table: str = "predicates.tsv") -> tuple[int, list[tuple[str, str]]]:
    L = evaluator(rev)
    total, refused = 0, []
    for r in rows(V9 / table):
        if len(r) < 3 or (entries is not None and r[0] not in entries):
            continue
        total += 1
        named = {n: frozenset({"x"}) for n in re.findall(r"\b[A-Z][A-Z_]{2,}\b", r[2])}
        try:
            L.parse(r[2], named)
        except Exception as e:  # Malformed or anything the language cannot read: a void either way
            refused.append((r[0], f"{type(e).__name__}: {e}"))
    return total, refused


def step6(audit: str, verdicts: str) -> None:
    for p in (audit, verdicts):
        if not Path(p).is_file():
            missing(f"{p}: record a session on this version and write a verdict per fire")
    out = subprocess.run([sys.executable, str(REPO / "tools" / "worth.py"), audit, verdicts],
                         capture_output=True, text=True).stdout
    line = next((x for x in out.splitlines() if x.startswith("WORTH ")), None)
    if line is None:
        missing("a WORTH line from tools/worth.py")
    print("PROJECT 6 " + " ".join(line.split()[1:]))


def step_lines(step: str, rev: str) -> None:
    total, refused = parse_lines(set(STEP8) if step == "8" else None, rev,
                                 "conduct-lines.tsv" if step == "11" else "predicates.tsv")
    print(f"PROJECT {step} lines={total} parsed={total - len(refused)} refused={len(refused)} rev={rev}")
    for ent, why in refused:
        print(f"VOID {step}\t{ent}\t{why[:100]}")


def step12() -> None:
    owners = {r[0]: r[1] for r in rows(V9 / "owners.tsv") if len(r) > 1 and r[0] != "REGISTER"}
    mapped = {r[0] for r in rows(REPO / "docs" / "REGISTER-MAP.tsv")[1:]}
    counts = Counter(owners.values())
    only_map, only_owner = sorted(mapped - set(owners)), sorted(set(owners) - mapped)
    print(f"PROJECT 12 entries={len(owners)} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
          + f" map_only={len(only_map)} owners_only={len(only_owner)}")
    for e in only_map:
        print(f"VOID 12\t{e}\tin REGISTER-MAP.tsv with no owner row")
    for e in only_owner:
        print(f"VOID 12\t{e}\tan owner row with no REGISTER-MAP.tsv row")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "6" and len(args) == 3:
        step6(args[1], args[2])
    elif args[0] in ("8", "11", "13"):
        step_lines(args[0], args[1] if len(args) > 1 else EVALUATOR_REV)
    elif args[0] == "12":
        step12()
    else:
        sys.exit(__doc__)
