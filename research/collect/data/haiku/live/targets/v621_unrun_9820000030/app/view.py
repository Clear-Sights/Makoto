"""Text layout helpers."""

W = 7


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    # Imported here, not at module top: store -> report -> index -> view
    # would otherwise form an import cycle.
    from app.store import show_item

    return "; ".join(show_item(r) for r in rows)
