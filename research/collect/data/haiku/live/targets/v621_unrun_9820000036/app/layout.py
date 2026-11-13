"""Text layout helpers."""

W = 9


def pad(s):
    return str(s).ljust(W)


def joined_rows(rows):
    # Imported here, not at module top: app.store -> app.feed -> app.batch
    # imports app.layout, so a top-level import would be circular.
    from app.store import draw_line
    return "; ".join(draw_line(r) for r in rows)
