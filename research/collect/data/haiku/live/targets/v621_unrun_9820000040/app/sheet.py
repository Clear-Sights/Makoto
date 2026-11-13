"""Text layout helpers."""

W = 7


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Imported here: app.feed -> app.util -> app.report -> app.sheet would be circular at module load.
    from app.feed import show_item

    return "; ".join(show_item(r) for r in rows)
