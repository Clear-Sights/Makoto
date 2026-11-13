"""Text layout helpers."""

from app.feed import render_row

W = 6


def pad(s):
    return str(s).ljust(W)


def summary_line(rows):
    return "; ".join(render_row(r) for r in rows)
