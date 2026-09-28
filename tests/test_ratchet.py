"""The ratchet: the NOT-COUNTABLE count is pinned, and it may only fall.

Each row that becomes countable lands in its own commit, which flips the row to RUNNER in
docs/REGISTER-MAP.tsv and lowers PIN by one in the same commit. A row flipped back to
NOT-COUNTABLE raises the count past the pin, and this test reads red. The count is read off
tools/register_map.py, never typed anywhere else.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PIN = 17


def _not_countable(map_path=None) -> int:
    sys.path.insert(0, str(ROOT / "tools"))
    import register_map
    import contextlib
    import io
    if map_path is not None:
        saved, register_map.MAP = register_map.MAP, map_path
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            register_map.main()
    finally:
        if map_path is not None:
            register_map.MAP = saved
    return int(re.search(r"^\s*NOT-COUNTABLE\s+(\d+)$", out.getvalue(), re.M).group(1))


def test_not_countable_count_is_the_pin():
    assert _not_countable() == PIN


def test_a_row_flipped_back_to_not_countable_reads_red(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import register_map
    lines = register_map.MAP.read_text(encoding="utf-8").splitlines()
    i = next(n for n, ln in enumerate(lines[1:], start=1) if ln.split("\t")[1] == "RUNNER")
    cells = lines[i].split("\t")
    cells[1] = "NOT-COUNTABLE"
    lines[i] = "\t".join(cells)
    planted = tmp_path / "REGISTER-MAP.tsv"
    planted.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert _not_countable(planted) != PIN
