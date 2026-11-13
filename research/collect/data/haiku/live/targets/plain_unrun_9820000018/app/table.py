"""Text layout helpers."""

from app.feed import make_entry

W = 12


def pad(s):
    return str(s).ljust(W)


def summary_line(rows):
    return "; ".join(make_entry(r) for r in rows)
