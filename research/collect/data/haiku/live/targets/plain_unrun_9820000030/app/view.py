"""Text layout helpers."""

W = 7


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    # Imported here: a top-level import would create a cycle
    # (store -> report -> index -> view -> store).
    from app.store import show_item

    return "; ".join(show_item(r) for r in rows)
