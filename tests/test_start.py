"""START's open steps each carry a projection, and every void it leaves is a row for an open step."""
from __future__ import annotations

import csv
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECTION = re.compile(r"^\s+projection[ :(]", re.M)


def open_steps(text: str) -> dict[str, str]:
    """Numbered steps not struck through, each with its whole body."""
    body = text.split("\nThe steps:\n", 1)[1]
    parts = re.split(r"^(\d+)\. ", body, flags=re.M)[1:]
    return {n: b for n, b in zip(parts[::2], parts[1::2]) if not b.startswith("~~")}


def test_every_open_step_carries_a_projection_line():
    steps = open_steps((REPO / "START.md").read_text(encoding="utf-8"))
    assert steps, "no open steps read"
    missing = [n for n, b in steps.items() if not PROJECTION.search(b)]
    assert not missing, f"open steps with no projection: {missing}"


def test_the_projection_check_reads_red_on_its_plant():
    planted = "The steps:\n6. Re-grade worth.\n   check: x. owner: next.\n"
    steps = open_steps("x\n" + planted)
    assert not PROJECTION.search(steps["6"])


def test_every_void_names_an_open_step_and_a_measure():
    steps = open_steps((REPO / "START.md").read_text(encoding="utf-8"))
    rows = list(csv.DictReader((REPO / "docs/v9/VOIDS.tsv").open(encoding="utf-8"), delimiter="\t"))
    assert rows
    for r in rows:
        assert r["step"] in steps, r
        assert r["void"] and r["measured_by"], r
