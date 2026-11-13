"""Text layout helpers."""

W = 11


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Imported here, not at module level: app.batch -> app.cache -> app.util
    # imports app.table, so a top-level import would be circular.
    from app.batch import draw_line
    return "; ".join(draw_line(r) for r in rows)
