"""Text layout helpers."""

W = 6


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    # Imported here: app.report -> app.util -> app.index -> app.render would be circular at module level.
    from app.report import show_item
    return "; ".join(show_item(r) for r in rows)
