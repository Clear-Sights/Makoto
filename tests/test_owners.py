"""docs/v9/owners.tsv is a join, never a reading (START step 12). Its Makoto half is checked here with
no Scour clone: an entry is owned by Makoto (`makoto` or `both`) exactly when docs/REGISTER-MAP.tsv
calls it RUNNER, and every map entry has one owner row. `python3 tools/owners.py` checks the Scour
half against the clone at its pin. Plant: a RUNNER flipped in the map reads red."""
from __future__ import annotations

import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _map(path=ROOT / "docs" / "REGISTER-MAP.tsv"):
    return {r[0]: r[1] for r in list(csv.reader(path.open(encoding="utf-8"), delimiter="\t"))[1:] if r and r[0]}


def _owners():
    return {r[0]: r[1] for r in csv.reader((ROOT / "docs/v9/owners.tsv").open(encoding="utf-8"), delimiter="\t")
            if len(r) > 1}


def mismatches(verdicts, owners):
    out = [e for e in verdicts if e not in owners] + [e for e in owners if e not in verdicts]
    return out + [e for e, v in verdicts.items() if e in owners
                  and (v == "RUNNER") != (owners[e] in ("makoto", "both"))]


def test_the_makoto_half_of_the_owner_table_is_the_map():
    assert mismatches(_map(), _owners()) == []


def test_plant_a_flipped_runner_reads_red():
    verdicts = _map()
    entry = next(e for e, v in verdicts.items() if v == "RUNNER")
    assert mismatches({**verdicts, entry: "NOT-COUNTABLE"}, _owners()) == [entry]


def test_every_witnessed_dedupe_is_one_dedupe_runs():
    sys.path.insert(0, str(ROOT / "tools"))
    import dedupe
    import owners
    assert set(dedupe.MAKOTO) == set(owners.WITNESSED)
