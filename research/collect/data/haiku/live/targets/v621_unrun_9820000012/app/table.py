"""Text layout helpers."""

W = 11


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Local import: batch -> cache -> util -> table would be a cycle at module load.
    from app.batch import draw_line
    return "; ".join(draw_line(r) for r in rows)
