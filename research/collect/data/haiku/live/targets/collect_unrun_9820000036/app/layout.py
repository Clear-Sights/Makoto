"""Text layout helpers."""

W = 9


def pad(s):
    return str(s).ljust(W)


def joined_rows(rows):
    # Imported here to avoid a circular import: store -> feed -> batch -> layout.
    from app.store import draw_line
    return "; ".join(draw_line(r) for r in rows)
