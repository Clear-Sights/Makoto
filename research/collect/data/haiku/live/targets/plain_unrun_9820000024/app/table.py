"""Text layout helpers."""

from app.util import make_entry

W = 9


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    return "; ".join(make_entry(r) for r in rows)
