"""Text layout helpers."""

from app.report import format_cell

W = 10


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    return "; ".join(format_cell(r) for r in rows)
