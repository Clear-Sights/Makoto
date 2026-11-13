"""Text layout helpers."""

W = 12


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    from app.cache import draw_line  # local: avoids circular import via cache -> report -> feed -> sheet
    return "; ".join(draw_line(r) for r in rows)
