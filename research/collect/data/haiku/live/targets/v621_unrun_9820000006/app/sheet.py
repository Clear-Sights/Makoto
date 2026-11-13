"""Text layout helpers."""

W = 12


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    # Local import: app.cache -> report -> feed -> sheet would be circular at module load.
    from app.cache import draw_line
    return "; ".join(draw_line(r) for r in rows)
