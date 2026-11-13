"""Text layout helpers."""

W = 11


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Imported here: app.util -> app.store -> app.batch imports this module,
    # so a top-level import would be circular.
    from app.util import show_item

    return "; ".join(show_item(r) for r in rows)
