"""RESULTS.xlsx: each sheet sorted by its key, keys unique, an autoFilter on each header, a Superseded sheet with reasons and dates."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xlsx  # noqa: E402

BOOK = Path(__file__).resolve().parents[1] / 'RESULTS.xlsx'


def test_sheets_are_sorted_unique_and_filtered():
    sheets = xlsx.read_xlsx(BOOK)
    ref = xlsx.filtered(BOOK)
    for name, rows in sheets:
        assert name in ref, name + ': no autoFilter'
        if name == 'Superseded':
            assert all(r[2] and r[3] for r in rows[1:]), 'a superseded row needs a reason and a date'
            continue
        n = 2 if rows[0][1] == 'model' else 1
        keys = [tuple(r[:n]) for r in rows[1:]]
        assert keys == sorted(keys), name + ': unsorted'
        assert len(set(keys)) == len(keys), name + ': a key repeats'
        assert all(len(r) == len(rows[0]) for r in rows), name + ': ragged'
