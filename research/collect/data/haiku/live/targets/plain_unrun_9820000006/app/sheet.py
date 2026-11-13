"""Text layout helpers."""

from app.cache import draw_line

W = 12


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    return "; ".join(draw_line(r) for r in rows)
