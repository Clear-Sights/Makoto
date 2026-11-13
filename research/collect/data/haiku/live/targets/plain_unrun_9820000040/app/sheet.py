"""Text layout helpers."""

W = 7


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Imported here: feed -> util -> report -> sheet forms a cycle at module level.
    from app.feed import show_item
    return "; ".join(show_item(r) for r in rows)
