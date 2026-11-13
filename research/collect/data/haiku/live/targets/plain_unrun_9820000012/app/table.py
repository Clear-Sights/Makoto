"""Text layout helpers."""

W = 11


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Imported here: app.batch -> app.cache -> app.util -> app.table would cycle at module level.
    from app.batch import draw_line
    return "; ".join(draw_line(r) for r in rows)
