"""Text layout helpers."""

W = 7


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    # Imported here: app.store -> app.report -> app.index -> app.view forms
    # an import cycle, so a module-level import would fail depending on load order.
    from app.store import show_item
    return "; ".join(show_item(r) for r in rows)
